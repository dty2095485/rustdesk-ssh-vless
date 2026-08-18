use anyhow::{Context, Result};
use russh::{
    keys::{PrivateKey, PublicKey},
    server::{self, Auth, ChannelOpenHandle, Msg, Server as _, Session},
    Channel, ChannelOpenFailure,
};
use std::{env, fs, sync::Arc};
use tokio::{
    self,
    net::{TcpListener, TcpStream},
};

// Built-in SSH gateway host key (ed25519). The client accepts any host key,
// so this only needs to be stable enough for the handshake.
// Injected at build time via env vars (see README.md); empty defaults fail
// the SSH gateway startup with a clear error instead of shipping a real key.
const HOST_PRIVATE_KEY: &str = match option_env!("RD_SSH_HOST_PRIVATE_KEY") {
    Some(s) => s,
    None => "",
};

// Matches the built-in client identity; clients ship with this private key.
const BUILTIN_AUTH_PUBLIC_KEY: &str = match option_env!("RD_SSH_PUBLIC_KEY") {
    Some(s) => s,
    None => "",
};

#[derive(Clone)]
struct Config {
    hbbs: String,
    nat: String,
    hbbr: String,
    authorized_keys: Vec<PublicKey>,
}

impl Config {
    fn from_env() -> Result<Self> {
        let mut authorized_keys = vec![PublicKey::from_openssh(BUILTIN_AUTH_PUBLIC_KEY)
            .context("Invalid built-in SSH authorized key")?];
        if let Some(path) = env::var("SSH_AUTHORIZED_KEYS")
            .ok()
            .filter(|s| !s.is_empty())
        {
            if let Ok(content) = fs::read_to_string(&path) {
                for line in content.lines() {
                    let line = line.trim();
                    if line.is_empty() || line.starts_with('#') {
                        continue;
                    }
                    if let Ok(key) = PublicKey::from_openssh(line) {
                        authorized_keys.push(key);
                    }
                }
            }
        }
        Ok(Self {
            // Forward to the key-exchange-free internal listeners (mirrors the
            // VLESS gateway): the SSH tunnel itself is the authentication.
            hbbs: value("SSH_HBBS", "127.0.0.1:22116"),
            nat: value("SSH_NAT", "127.0.0.1:22115"),
            hbbr: value("SSH_HBBR", "127.0.0.1:22117"),
            authorized_keys,
        })
    }
}

#[derive(Clone)]
struct Server {
    config: Arc<Config>,
}

impl server::Server for Server {
    type Handler = Self;

    fn new_client(&mut self, _: Option<std::net::SocketAddr>) -> Self {
        self.clone()
    }

    fn handle_session_error(&mut self, error: <Self::Handler as server::Handler>::Error) {
        log::debug!("SSH session error: {error:#}");
    }
}

impl server::Handler for Server {
    type Error = russh::Error;

    async fn auth_publickey(
        &mut self,
        _user: &str,
        key: &PublicKey,
    ) -> Result<Auth, Self::Error> {
        // Compare key data only: the wire blob carries no comment, while the
        // authorized_keys entries may include one.
        if self.config.authorized_keys.iter().any(|k| k.key_data() == key.key_data()) {
            Ok(Auth::Accept)
        } else {
            Ok(Auth::reject())
        }
    }

    async fn channel_open_direct_tcpip(
        &mut self,
        channel: Channel<Msg>,
        _host_to_connect: &str,
        port_to_connect: u32,
        _originator_address: &str,
        _originator_port: u32,
        reply: ChannelOpenHandle,
        _session: &mut Session,
    ) -> Result<(), Self::Error> {
        // Same port mapping as the VLESS gateway.
        let upstream = match port_to_connect {
            21116 => &self.config.hbbs,
            21115 => &self.config.nat,
            21117 | 8443 | 443 => &self.config.hbbr,
            _ => {
                log::warn!("Rejected SSH direct-tcpip to unpermitted port {port_to_connect}");
                reply.reject(ChannelOpenFailure::AdministrativelyProhibited).await;
                return Ok(());
            }
        };
        let mut upstream = match TcpStream::connect(upstream).await {
            Ok(stream) => stream,
            Err(err) => {
                log::warn!("SSH upstream connect to {upstream} failed: {err:#}");
                reply.reject(ChannelOpenFailure::ConnectFailed).await;
                return Ok(());
            }
        };
        upstream.set_nodelay(true).ok();
        reply.accept().await;
        tokio::spawn(async move {
            let mut stream = channel.into_stream();
            if let Err(err) = tokio::io::copy_bidirectional(&mut stream, &mut upstream).await {
                log::debug!("SSH tunnel closed: {err:#}");
            }
        });
        Ok(())
    }
}

#[tokio::main(flavor = "multi_thread")]
async fn main() -> Result<()> {
    env_logger::Builder::from_env(env_logger::Env::default().default_filter_or("info")).init();
    let config = Config::from_env()?;
    let host_key = PrivateKey::from_openssh(HOST_PRIVATE_KEY)
        .context("Invalid built-in SSH host key")?;
    let server_config = Arc::new(server::Config {
        keys: vec![host_key],
        inactivity_timeout: None,
        ..Default::default()
    });
    let listener = TcpListener::bind(value("SSH_LISTEN", "0.0.0.0:22")).await?;
    log::info!("SSH gateway listening on {}", listener.local_addr()?);
    let mut server = Server {
        config: Arc::new(config),
    };
    server.run_on_socket(server_config, &listener).await?;
    Ok(())
}

fn value(name: &str, default: &str) -> String {
    env::var(name).unwrap_or_else(|_| default.to_owned())
}
