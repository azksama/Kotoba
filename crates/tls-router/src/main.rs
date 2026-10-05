use clap::Parser;
use std::{collections::HashMap, io::{self,Cursor}, net::{IpAddr,SocketAddr}, sync::{Arc,Mutex}, time::Duration};
use tokio::{io::{AsyncReadExt,AsyncWriteExt},net::{TcpListener,TcpStream},sync::Semaphore,time::timeout};

#[derive(Parser,Clone)]
struct Args {
    #[arg(long)] bind: SocketAddr,
    #[arg(long)] kotoba_name: String,
    #[arg(long,default_value="127.0.0.1:48736")] kotoba: SocketAddr,
    #[arg(long,default_value="127.0.0.1:8189")] mochi: SocketAddr,
}
fn invalid() -> io::Error {io::Error::new(io::ErrorKind::InvalidData,"invalid TLS ClientHello")}
fn route(name:Option<&str>,args:&Args)->io::Result<SocketAddr>{
    match name {
        Some(n) if n.eq_ignore_ascii_case(&args.kotoba_name)=>Ok(args.kotoba),
        None=>Ok(args.mochi),
        _=>Err(invalid()),
    }
}
async fn client_hello(stream:&mut TcpStream)->io::Result<(Option<String>,Vec<u8>)>{
    let mut acceptor=rustls::server::Acceptor::default();
    let mut bytes=Vec::new();
    let mut chunk=[0u8;4096];
    loop {
        let n=stream.read(&mut chunk).await?;
        if n==0 || bytes.len()+n>65536{return Err(invalid())}
        bytes.extend_from_slice(&chunk[..n]);
        let mut cursor=Cursor::new(&chunk[..n]);
        while cursor.position()<(n as u64) {
            if acceptor.read_tls(&mut cursor)?==0{return Err(invalid())}
            match acceptor.accept(){
                Ok(Some(hello))=>return Ok((hello.client_hello().server_name().map(str::to_owned),bytes)),
                Ok(None)=>{},
                Err(_)=>return Err(invalid()),
            }
        }
    }
}
async fn pump<R:tokio::io::AsyncRead+Unpin,W:tokio::io::AsyncWrite+Unpin>(mut read:R,mut write:W)->io::Result<()> {
    let mut buffer=[0u8;32768];
    loop {
        let n=timeout(Duration::from_secs(300),read.read(&mut buffer)).await??;
        if n==0 {write.shutdown().await?;return Ok(())}
        timeout(Duration::from_secs(60),write.write_all(&buffer[..n])).await??;
    }
}
async fn forward(mut client:TcpStream,args:Arc<Args>)->io::Result<()> {
    let (name,bytes)=timeout(Duration::from_secs(5),client_hello(&mut client)).await??;
    let target=route(name.as_deref(),&args)?;
    let mut backend=timeout(Duration::from_secs(3),TcpStream::connect(target)).await??;
    timeout(Duration::from_secs(5),backend.write_all(&bytes)).await??;
    let (cr,cw)=client.split();let (br,bw)=backend.split();
    tokio::try_join!(pump(cr,bw),pump(br,cw))?;
    Ok(())
}
struct IpPermit {ip:IpAddr,counts:Arc<Mutex<HashMap<IpAddr,usize>>>}
impl Drop for IpPermit {fn drop(&mut self){if let Ok(mut counts)=self.counts.lock(){if let Some(n)=counts.get_mut(&self.ip){*n-=1;if *n==0{counts.remove(&self.ip);}}}}}
#[tokio::main]
async fn main()->io::Result<()> {
    let args=Arc::new(Args::parse());
    if !args.kotoba.ip().is_loopback() || !args.mochi.ip().is_loopback() || args.kotoba_name.parse::<IpAddr>().is_ok() || args.kotoba_name.is_empty(){return Err(invalid())}
    let listener=TcpListener::bind(args.bind).await?;
    let capacity=Arc::new(Semaphore::new(128));
    let counts=Arc::new(Mutex::new(HashMap::<IpAddr,usize>::new()));
    println!("TLS passthrough listening on {} (no private keys loaded)",args.bind);
    loop {
        let (client,peer)=listener.accept().await?;
        let Ok(slot)=capacity.clone().try_acquire_owned() else {continue};
        let allowed={let mut c=counts.lock().unwrap();let n=c.entry(peer.ip()).or_default();if *n>=16{false}else{*n+=1;true}};
        if !allowed{continue}
        let ip_permit=IpPermit{ip:peer.ip(),counts:counts.clone()};
        let args=args.clone();
        tokio::spawn(async move {let _slot=slot;let _ip=ip_permit;let _=forward(client,args).await;});
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    fn args()->Args{Args{bind:"127.0.0.1:18189".parse().unwrap(),kotoba_name:"kotoba.example.com".into(),kotoba:"127.0.0.1:48736".parse().unwrap(),mochi:"127.0.0.1:8189".parse().unwrap()}}
    #[test] fn routes_exact_sni_and_preserves_no_sni_mochi(){let a=args();assert_eq!(route(Some("KOTOBA.EXAMPLE.COM"),&a).unwrap(),a.kotoba);assert_eq!(route(None,&a).unwrap(),a.mochi);assert!(route(Some("evil.example.com"),&a).is_err());}
    #[tokio::test] async fn fragmented_hello_is_replayed_byte_for_byte(){
        let _=rustls::crypto::ring::default_provider().install_default();
        let cfg=rustls::ClientConfig::builder().with_root_certificates(rustls::RootCertStore::empty()).with_no_client_auth();
        let mut tls=rustls::ClientConnection::new(Arc::new(cfg),"kotoba.example.com".try_into().unwrap()).unwrap();
        let mut wire=Vec::new();tls.write_tls(&mut wire).unwrap();
        let listener=TcpListener::bind("127.0.0.1:0").await.unwrap();let address=listener.local_addr().unwrap();let original=wire.clone();
        let task=tokio::spawn(async move{let(mut s,_)=listener.accept().await.unwrap();client_hello(&mut s).await.unwrap()});
        let mut c=TcpStream::connect(address).await.unwrap();for b in wire {c.write_all(&[b]).await.unwrap();}
        let(name,replay)=task.await.unwrap();assert_eq!(name.as_deref(),Some("kotoba.example.com"));assert_eq!(replay,original);
    }
}
