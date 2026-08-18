use crate::{bail, config::SshServer, tcp::FramedStream, ResultType};
use russh::{client, keys::PrivateKeyWithHashAlg};
use std::sync::Arc;
use tokio::net::TcpStream;

struct ClientHandler;

impl client::Handler for ClientHandler {
    type Error = russh::Error;

    async fn check_server_key(
        &mut self,
        _key: &russh::keys::PublicKey,
    ) -> Result<bool, Self::Error> {
        // Self-hosted gateway; the tunnel itself is the trust boundary.
        Ok(true)
    }
}

pub async fn connect(
    target: &str,
    config: &SshServer,
    ms_timeout: u64,
) -> ResultType<FramedStream> {
    let endpoint = format!("{}:{}", config.server, config.port);
    let stream = crate::timeout(ms_timeout, TcpStream::connect(&endpoint))
        .await
        .map_err(|_| anyhow::anyhow!("Timed out connecting to SSH server"))??;
    stream.set_nodelay(true).ok();
    let local_addr = stream.local_addr()?;

    let key = russh::keys::PrivateKey::from_openssh(&config.private_key)
        .map_err(|_| anyhow::anyhow!("Invalid SSH private key"))?;
    let client_config = Arc::new(client::Config {
        nodelay: true,
        ..Default::default()
    });
    let mut session = crate::timeout(
        ms_timeout,
        client::connect_stream(client_config, stream, ClientHandler),
    )
    .await
    .map_err(|_| anyhow::anyhow!("Timed out negotiating SSH"))??;
    let auth = crate::timeout(
        ms_timeout,
        session.authenticate_publickey(
            config.username.clone(),
            PrivateKeyWithHashAlg::new(Arc::new(key), None),
        ),
    )
    .await
    .map_err(|_| anyhow::anyhow!("Timed out authenticating SSH"))??;
    if !auth.success() {
        bail!("SSH server rejected the public key");
    }
    let (host, port) = split_target(target)?;
    let channel = crate::timeout(
        ms_timeout,
        session.channel_open_direct_tcpip(host, port as u32, "0.0.0.0".to_owned(), 0u32),
    )
    .await
    .map_err(|_| anyhow::anyhow!("Timed out opening SSH channel"))??;
    // Keep the session alive: dropping the russh Handle closes the SSH
    // connection, which would immediately tear down the channel we return.
    std::mem::forget(session);
    Ok(FramedStream::from(channel.into_stream(), local_addr))
}

fn split_target(target: &str) -> ResultType<(String, u16)> {
    if let Ok(address) = target.parse::<std::net::SocketAddr>() {
        return Ok((address.ip().to_string(), address.port()));
    }
    let (host, port) = target
        .rsplit_once(':')
        .ok_or_else(|| anyhow::anyhow!("SSH target must include a port"))?;
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
