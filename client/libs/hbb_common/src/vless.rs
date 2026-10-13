use crate::{bail, config::VlessServer, tcp::FramedStream, verifier, ResultType};
use std::{
    convert::TryFrom,
    io,
    pin::Pin,
    task::{Context, Poll},
};
use tokio::{
    io::{AsyncRead, AsyncWrite, AsyncWriteExt, ReadBuf},
    net::TcpStream,
};
use tokio_rustls::TlsConnector;

pub async fn connect(
    target: &str,
    config: &VlessServer,
    ms_timeout: u64,
) -> ResultType<FramedStream> {
    if crate::config::Config::get_option("vless-transport") == "reality" {
        return crate::vless_reality::connect(target, config, ms_timeout).await;
    }
    let endpoint = format!("{}:{}", config.server, config.port);
    let stream = crate::timeout(ms_timeout, TcpStream::connect(&endpoint))
        .await
        .map_err(|_| anyhow::anyhow!("Timed out connecting to VLESS server"))??;
    // RustDesk's login and relay handshake consists of several small frames.
    // Match the direct TCP transport and avoid Nagle/delayed-ACK stalls on
    // mobile or carrier NAT networks.
    stream.set_nodelay(true).ok();
    let local_addr = stream.local_addr()?;
    let server_name = if config.server_name.is_empty() {
        config.server.as_str()
    } else {
        config.server_name.as_str()
    };
    let server_name = rustls_pki_types::ServerName::try_from(server_name.to_owned())?;
    let client_config = verifier::client_config_safe()?;
    let connector = TlsConnector::from(std::sync::Arc::new(client_config));
    let mut stream = crate::timeout(ms_timeout, connector.connect(server_name, stream))
        .await
        .map_err(|_| anyhow::anyhow!("Timed out negotiating VLESS TLS"))??;

    let (host, port) = split_target(target)?;
    let uuid = uuid::Uuid::parse_str(&config.uuid)?;
    let mut request = Vec::with_capacity(32 + host.len());
    request.push(0);
    request.extend_from_slice(uuid.as_bytes());
    request.push(0);
    request.push(1);
    request.extend_from_slice(&port.to_be_bytes());
    if let Ok(address) = host.parse::<std::net::IpAddr>() {
        match address {
            std::net::IpAddr::V4(address) => {
                request.push(1);
                request.extend_from_slice(&address.octets());
            }
            std::net::IpAddr::V6(address) => {
                request.push(3);
                request.extend_from_slice(&address.octets());
            }
        }
    } else {
        let host = host.as_bytes();
        if host.len() > u8::MAX as usize {
            bail!("VLESS target hostname is too long");
        }
        request.push(2);
        request.push(host.len() as u8);
        request.extend_from_slice(host);
    }
    stream.write_all(&request).await?;
    stream.flush().await?;
    Ok(FramedStream::from(
        VlessResponseStream::new(stream),
        local_addr,
    ))
}

// Xray can defer its response header until the upstream sends data.
struct VlessResponseStream<S> {
    inner: S,
    header: [u8; 2],
    header_read: usize,
    addons_remaining: usize,
    header_done: bool,
    failed: Option<io::ErrorKind>,
}

impl<S> VlessResponseStream<S> {
    fn new(inner: S) -> Self {
        Self {
            inner,
            header: [0; 2],
            header_read: 0,
            addons_remaining: 0,
            header_done: false,
            failed: None,
        }
    }

    fn reject(&mut self, error: io::Error) -> Poll<io::Result<()>> {
        self.failed = Some(error.kind());
        Poll::Ready(Err(error))
    }
}

impl<S: AsyncRead + Unpin> AsyncRead for VlessResponseStream<S> {
    fn poll_read(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        buf: &mut ReadBuf<'_>,
    ) -> Poll<io::Result<()>> {
        if buf.remaining() == 0 {
            return Poll::Ready(Ok(()));
        }
        let this = self.get_mut();
        if let Some(kind) = this.failed {
            return Poll::Ready(Err(io::Error::new(kind, "Invalid VLESS response")));
        }
        if !this.header_done {
            while this.header_read < this.header.len() {
                let mut response = ReadBuf::new(&mut this.header[this.header_read..]);
                match Pin::new(&mut this.inner).poll_read(cx, &mut response) {
                    Poll::Pending => return Poll::Pending,
                    Poll::Ready(Err(error)) => return this.reject(error),
                    Poll::Ready(Ok(())) => {}
                }
                let count = response.filled().len();
                if count == 0 {
                    return this.reject(io::Error::new(
                        io::ErrorKind::UnexpectedEof,
                        "Truncated VLESS response header",
                    ));
                }
                this.header_read += count;
                if this.header[0] != 0 {
                    return this.reject(io::Error::new(
                        io::ErrorKind::InvalidData,
                        "Unsupported VLESS response version",
                    ));
                }
            }
            this.addons_remaining = this.header[1] as usize;
            this.header_done = true;
        }
        while this.addons_remaining > 0 {
            let mut ignored = [0; u8::MAX as usize];
            let mut response = ReadBuf::new(&mut ignored[..this.addons_remaining]);
            match Pin::new(&mut this.inner).poll_read(cx, &mut response) {
                Poll::Pending => return Poll::Pending,
                Poll::Ready(Err(error)) => return this.reject(error),
                Poll::Ready(Ok(())) => {}
            }
            let count = response.filled().len();
            if count == 0 {
                return this.reject(io::Error::new(
                    io::ErrorKind::UnexpectedEof,
                    "Truncated VLESS response addons",
                ));
            }
            this.addons_remaining -= count;
        }
        Pin::new(&mut this.inner).poll_read(cx, buf)
    }
}

impl<S: AsyncWrite + Unpin> AsyncWrite for VlessResponseStream<S> {
    fn poll_write(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        buf: &[u8],
    ) -> Poll<io::Result<usize>> {
        Pin::new(&mut self.get_mut().inner).poll_write(cx, buf)
    }

    fn poll_flush(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        Pin::new(&mut self.get_mut().inner).poll_flush(cx)
    }

    fn poll_shutdown(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        Pin::new(&mut self.get_mut().inner).poll_shutdown(cx)
    }

    fn is_write_vectored(&self) -> bool {
        self.inner.is_write_vectored()
    }

    fn poll_write_vectored(
        self: Pin<&mut Self>,
        cx: &mut Context<'_>,
        bufs: &[io::IoSlice<'_>],
    ) -> Poll<io::Result<usize>> {
        Pin::new(&mut self.get_mut().inner).poll_write_vectored(cx, bufs)
    }
}

fn split_target(target: &str) -> ResultType<(String, u16)> {
    if let Ok(address) = target.parse::<std::net::SocketAddr>() {
        return Ok((address.ip().to_string(), address.port()));
    }
    let (host, port) = target
        .rsplit_once(':')
        .ok_or_else(|| anyhow::anyhow!("VLESS target must include a port"))?;
    let port = port.parse::<u16>()?;
    Ok((host.trim_matches(['[', ']']).to_owned(), port))
}

#[cfg(test)]
mod tests {
    use super::{split_target, VlessResponseStream};
    use std::{
        io,
        pin::Pin,
        task::{Context, Poll},
        time::Duration,
    };
    use tokio::{
        io::{duplex, AsyncRead, AsyncReadExt, AsyncWriteExt, DuplexStream, ReadBuf},
        time::timeout,
    };

    #[test]
    fn response_stream_retains_transport_traits() {
        fn check<T: Send + Sync + Unpin + AsyncRead + tokio::io::AsyncWrite>() {}
        check::<VlessResponseStream<DuplexStream>>();
    }

    #[tokio::test]
    async fn response_read_errors_are_preserved() {
        struct FailedRead;
        impl AsyncRead for FailedRead {
            fn poll_read(
                self: Pin<&mut Self>,
                _cx: &mut Context<'_>,
                _buf: &mut ReadBuf<'_>,
            ) -> Poll<io::Result<()>> {
                Poll::Ready(Err(io::Error::new(
                    io::ErrorKind::ConnectionReset,
                    "test transport reset",
                )))
            }
        }
        let mut client = VlessResponseStream::new(FailedRead);
        for _ in 0..2 {
            assert_eq!(
                client.read(&mut [0; 1]).await.unwrap_err().kind(),
                io::ErrorKind::ConnectionReset
            );
        }
    }

    #[tokio::test]
    async fn delayed_response_allows_client_first_request() {
        let (client, mut server) = duplex(64);
        let server = tokio::spawn(async move {
            let mut request = [0; 5];
            server.read_exact(&mut request).await.unwrap();
            assert_eq!(&request, b"hello");
            server.write_all(b"\x00\x00world").await.unwrap();
        });
        let mut client = VlessResponseStream::new(client);
        timeout(Duration::from_secs(1), async {
            client.write_all(b"hello").await.unwrap();
            client.flush().await.unwrap();
            let mut response = [0; 5];
            client.read_exact(&mut response).await.unwrap();
            assert_eq!(&response, b"world");
        })
        .await
        .unwrap();
        server.await.unwrap();
    }

    #[tokio::test]
    async fn fragmented_header_and_addons_are_not_payload() {
        let (client, mut server) = duplex(64);
        let mut client = VlessResponseStream::new(client);
        let mut response = [0; 5];
        for part in [b"\x00".as_slice(), b"\x03", b"a", b"bc"] {
            server.write_all(part).await.unwrap();
            assert!(
                timeout(Duration::from_millis(10), client.read(&mut response))
                    .await
                    .is_err()
            );
        }
        server.write_all(b"world").await.unwrap();
        client.read_exact(&mut response).await.unwrap();
        assert_eq!(&response, b"world");
        server.shutdown().await.unwrap();
        assert_eq!(client.read(&mut response).await.unwrap(), 0);
    }

    #[tokio::test]
    async fn immediate_legacy_response_does_not_block_writes() {
        let (client, mut server) = duplex(64);
        server.write_all(b"\x00\x00").await.unwrap();
        let mut client = VlessResponseStream::new(client);
        client.write_all(b"request").await.unwrap();
        let mut request = [0; 7];
        server.read_exact(&mut request).await.unwrap();
        assert_eq!(&request, b"request");
        server.write_all(b"ok").await.unwrap();
        let mut response = [0; 2];
        client.read_exact(&mut response).await.unwrap();
        assert_eq!(&response, b"ok");
    }

    #[tokio::test]
    async fn complete_header_without_payload_is_normal_eof() {
        let (client, mut server) = duplex(64);
        server.write_all(b"\x00\x00").await.unwrap();
        server.shutdown().await.unwrap();
        let mut client = VlessResponseStream::new(client);
        assert_eq!(client.read(&mut [0; 1]).await.unwrap(), 0);
    }

    #[tokio::test]
    async fn invalid_version_never_becomes_payload() {
        let (client, mut server) = duplex(64);
        server.write_all(b"\x01\x00bad").await.unwrap();
        let mut client = VlessResponseStream::new(client);
        for _ in 0..2 {
            assert_eq!(
                client.read(&mut [0; 8]).await.unwrap_err().kind(),
                io::ErrorKind::InvalidData
            );
        }
    }

    #[tokio::test]
    async fn truncated_header_or_addons_returns_unexpected_eof() {
        for bytes in [b"".as_slice(), b"\x00", b"\x00\x02a"] {
            let (client, mut server) = duplex(64);
            server.write_all(bytes).await.unwrap();
            server.shutdown().await.unwrap();
            let mut client = VlessResponseStream::new(client);
            assert_eq!(
                client.read(&mut [0; 1]).await.unwrap_err().kind(),
                io::ErrorKind::UnexpectedEof
            );
        }
    }

    #[tokio::test]
    async fn zero_capacity_read_preserves_header_state() {
        let (client, mut server) = duplex(64);
        let mut client = VlessResponseStream::new(client);
        let mut empty = [];
        let mut buf = ReadBuf::new(&mut empty);
        futures::future::poll_fn(|cx| Pin::new(&mut client).poll_read(cx, &mut buf))
            .await
            .unwrap();
        assert_eq!(client.header_read, 0);
        server.write_all(b"\x00\x00ok").await.unwrap();
        let mut response = [0; 2];
        client.read_exact(&mut response).await.unwrap();
        assert_eq!(&response, b"ok");
    }

    #[test]
    fn split_target_supports_domains_and_ipv6() {
        assert_eq!(
            split_target("relay.example.com:21117").unwrap(),
            ("relay.example.com".into(), 21117)
        );
        assert_eq!(split_target("[::1]:21116").unwrap(), ("::1".into(), 21116));
    }
}
