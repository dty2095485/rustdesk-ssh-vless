use crate::{bail, config::VlessServer, tcp::FramedStream, verifier, ResultType};
use std::convert::TryFrom;
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::TcpStream,
};
use tokio_rustls::TlsConnector;

pub async fn connect(
    target: &str,
    config: &VlessServer,
    ms_timeout: u64,
) -> ResultType<FramedStream> {
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
    let connector = TlsConnector::from(std::sync::Arc::new(verifier::client_config_safe()?));
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
    let mut response = [0_u8; 2];
    stream.read_exact(&mut response).await?;
    if response != [0, 0] {
        bail!("VLESS server rejected the connection");
    }
    Ok(FramedStream::from(stream, local_addr))
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
    use super::split_target;

    #[test]
    fn split_target_supports_domains_and_ipv6() {
        assert_eq!(
            split_target("relay.example.com:21117").unwrap(),
            ("relay.example.com".into(), 21117)
        );
        assert_eq!(split_target("[::1]:21116").unwrap(), ("::1".into(), 21116));
    }
}
