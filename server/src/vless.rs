use hbb_common::{
    anyhow::{bail, Context, Result},
    log,
    tokio::{
        self,
        io::{AsyncRead, AsyncReadExt, AsyncWriteExt},
        net::{TcpListener, TcpStream},
        sync::Semaphore,
        time::timeout,
    },
};
use std::{env, fs::File, io::BufReader, sync::Arc, time::Duration};
use tokio_rustls::{rustls, TlsAcceptor};

#[tokio::main(flavor = "multi_thread")]
async fn main() -> Result<()> {
    let config = Config::from_env()?;
    let listener = TcpListener::bind(&config.listen).await?;
    let acceptor = TlsAcceptor::from(Arc::new(load_tls_config(&config.cert, &config.key)?));
    let connection_slots = Arc::new(Semaphore::new(config.max_connections));
    log::info!("VLESS TLS listener active on {}", listener.local_addr()?);
    log::info!(
        "VLESS limits: max_connections={}, tls_handshake_timeout={}s, header_timeout={}s, upstream_connect_timeout={}s",
        config.max_connections,
        config.tls_handshake_timeout.as_secs(),
        config.header_timeout.as_secs(),
        config.upstream_connect_timeout.as_secs()
    );
    loop {
        let (stream, addr) = listener.accept().await?;
        let permit = match connection_slots.clone().try_acquire_owned() {
            Ok(permit) => permit,
            Err(err) => {
                log::warn!(
                    "Rejected VLESS connection from {addr}: concurrent connection limit reached ({err})"
                );
                continue;
            }
        };
        let acceptor = acceptor.clone();
        let config = config.clone();
        tokio::spawn(async move {
            let _permit = permit;
            if let Err(err) = handle(stream, acceptor, config).await {
                log::debug!("Rejected VLESS connection from {addr}: {err:#}");
            }
        });
    }
}

#[derive(Clone)]
struct Config {
    listen: String,
    uuid: uuid::Uuid,
    cert: String,
    key: String,
    hbbs: String,
    nat: String,
    hbbr: String,
    tls_handshake_timeout: Duration,
    header_timeout: Duration,
    upstream_connect_timeout: Duration,
    max_connections: usize,
}

impl Config {
    fn from_env() -> Result<Self> {
        Ok(Self {
            listen: value("VLESS_LISTEN", "0.0.0.0:443"),
            uuid: value("VLESS_UUID", "")
                .parse()
                .context("VLESS_UUID must be a UUID")?,
            cert: required("VLESS_CERT")?,
            key: required("VLESS_KEY")?,
            hbbs: value("VLESS_HBBS", "127.0.0.1:21116"),
            nat: value("VLESS_NAT", "127.0.0.1:21115"),
            hbbr: value("VLESS_HBBR", "127.0.0.1:21117"),
            tls_handshake_timeout: duration_from_env("VLESS_TLS_HANDSHAKE_TIMEOUT_SECS", "10")?,
            header_timeout: duration_from_env("VLESS_HEADER_TIMEOUT_SECS", "10")?,
            upstream_connect_timeout: duration_from_env(
                "VLESS_UPSTREAM_CONNECT_TIMEOUT_SECS",
                "5",
            )?,
            max_connections: positive_usize("VLESS_MAX_CONNECTIONS", "1024")?,
        })
    }
}

async fn handle(stream: TcpStream, acceptor: TlsAcceptor, config: Config) -> Result<()> {
    // Relay and login handshakes contain small latency-sensitive frames.
    // Keep the tunnel behavior consistent with RustDesk's direct TCP path.
    stream.set_nodelay(true).ok();
    let mut stream = timeout(config.tls_handshake_timeout, acceptor.accept(stream))
        .await
        .context("TLS handshake timed out")??;
    let port = timeout(
        config.header_timeout,
        read_request(&mut stream, config.uuid),
    )
    .await
    .context("VLESS request header timed out")??;
    let upstream = match port {
        21116 => &config.hbbs,
        // NAT-type TCP probe (official clients connect to 21115).
        21115 => &config.nat,
        // Relay target: direct mode dials 443 raw (nginx routes non-TLS to
        // hbbr), VLESS clients address the same 443 inside the tunnel.
        21117 | 8443 | 443 => &config.hbbr,
        _ => bail!("VLESS destination port is not permitted"),
    };
    let mut upstream = timeout(
        config.upstream_connect_timeout,
        TcpStream::connect(upstream),
    )
    .await
    .context("VLESS upstream connection timed out")??;
    upstream.set_nodelay(true).ok();
    stream.write_all(&[0, 0]).await?;
    stream.flush().await?;
    let (client_to_upstream, upstream_to_client) =
        tokio::io::copy_bidirectional(&mut stream, &mut upstream).await?;
    // This is intentionally Info: VLESS close accounting is needed in normal
    // container logs to distinguish an upstream relay close from a client-side
    // TCP reset while diagnosing production sessions.
    log::info!(
        "VLESS tunnel closed: destination_port={}, client_to_upstream={}, upstream_to_client={}",
        port,
        client_to_upstream,
        upstream_to_client
    );
    Ok(())
}

async fn read_request<S>(stream: &mut S, expected_uuid: uuid::Uuid) -> Result<u16>
where
    S: AsyncRead + Unpin,
{
    let mut header = [0_u8; 18];
    stream.read_exact(&mut header).await?;
    if header[0] != 0 || uuid::Uuid::from_slice(&header[1..17])? != expected_uuid {
        bail!("Invalid VLESS credential");
    }
    let mut ignored = vec![0_u8; header[17] as usize];
    stream.read_exact(&mut ignored).await?;
    let mut command = [0_u8; 3];
    stream.read_exact(&mut command).await?;
    if command[0] != 1 {
        bail!("Only VLESS TCP requests are supported");
    }
    let mut address_type = [0_u8; 1];
    stream.read_exact(&mut address_type).await?;
    let address_len = match address_type[0] {
        1 => 4,
        2 => {
            let mut len = [0_u8; 1];
            stream.read_exact(&mut len).await?;
            len[0] as usize
        }
        3 => 16,
        _ => bail!("Unsupported VLESS address type"),
    };
    let mut ignored = vec![0_u8; address_len];
    stream.read_exact(&mut ignored).await?;
    Ok(u16::from_be_bytes([command[1], command[2]]))
}

fn load_tls_config(cert_path: &str, key_path: &str) -> Result<rustls::ServerConfig> {
    let mut cert_reader = BufReader::new(File::open(cert_path)?);
    let certs = rustls_pemfile::certs(&mut cert_reader).collect::<Result<Vec<_>, _>>()?;
    let mut key_reader = BufReader::new(File::open(key_path)?);
    let key = rustls_pemfile::private_key(&mut key_reader)?.context("No private key found")?;
    Ok(rustls::ServerConfig::builder()
        .with_no_client_auth()
        .with_single_cert(certs, key)?)
}

fn value(name: &str, default: &str) -> String {
    env::var(name).unwrap_or_else(|_| default.to_owned())
}

fn required(name: &str) -> Result<String> {
    let value = value(name, "");
    if value.is_empty() {
        bail!("{name} is required");
    }
    Ok(value)
}

fn duration_from_env(name: &str, default: &str) -> Result<Duration> {
    let seconds = value(name, default)
        .parse::<u64>()
        .with_context(|| format!("{name} must be a positive integer number of seconds"))?;
    if seconds == 0 {
        bail!("{name} must be greater than zero");
    }
    Ok(Duration::from_secs(seconds))
}

fn positive_usize(name: &str, default: &str) -> Result<usize> {
    let parsed = value(name, default)
        .parse::<usize>()
        .with_context(|| format!("{name} must be a positive integer"))?;
    if parsed == 0 {
        bail!("{name} must be greater than zero");
    }
    Ok(parsed)
}
