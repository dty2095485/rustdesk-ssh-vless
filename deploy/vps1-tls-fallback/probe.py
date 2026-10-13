"""Read-only, standard-library TLS/fallback smoke tests for VPS1.

Production: python probe.py
Candidate via SSH 13443 -> VPS 127.0.0.1:18443:
    python probe.py --address 127.0.0.1 --port 13443 --http2

No credentials, browser body, or private keys are printed. The default browser
reference is the unchanged example.com website on public port 443.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import socket
import ssl
import struct
import time
import uuid


DEFAULT_PROFILE = Path(r"<workspace>\releases\windows\ssh\VPS1-network.json")
MAX_BODY = 4 * 1024 * 1024


def exact(stream, size):
    result = bytearray()
    while len(result) < size:
        piece = stream.recv(size - len(result))
        if not piece:
            raise RuntimeError("peer closed before complete response")
        result.extend(piece)
    return bytes(result)


def frame(payload):
    length = len(payload)
    count = next(n for n in range(1, 5) if length < 1 << (8 * n - 2))
    return ((length << 2) | (count - 1)).to_bytes(count, "little") + payload


def recv_frame(stream):
    first = exact(stream, 1)
    count = (first[0] & 3) + 1
    length = int.from_bytes(first + exact(stream, count - 1), "little") >> 2
    if length > MAX_BODY:
        raise RuntimeError("unexpectedly large RustDesk protocol response")
    return exact(stream, length)


def protobuf_varint(value):
    output = bytearray()
    while value >= 128:
        output.append((value & 127) | 128)
        value >>= 7
    output.append(value)
    return bytes(output)


def protobuf_text(number, value):
    value = value.encode("utf-8")
    return protobuf_varint((number << 3) | 2) + protobuf_varint(len(value)) + value


def tls_socket(address, port, sni, alpn, timeout):
    context = ssl.create_default_context()
    if alpn:
        context.set_alpn_protocols(alpn)
    raw = socket.create_connection((address, port), timeout=timeout)
    try:
        return context.wrap_socket(raw, server_hostname=sni)
    except BaseException:
        raw.close()
        raise


def dechunk(body):
    result = bytearray()
    offset = 0
    while True:
        end = body.find(b"\r\n", offset)
        if end < 0:
            raise RuntimeError("incomplete HTTP chunk size")
        length = int(body[offset:end].split(b";", 1)[0], 16)
        if length == 0:
            return bytes(result)
        offset = end + 2
        if offset + length + 2 > len(body):
            raise RuntimeError("incomplete HTTP chunk body")
        result.extend(body[offset:offset + length])
        offset += length
        if body[offset:offset + 2] != b"\r\n":
            raise RuntimeError("invalid HTTP chunk boundary")
        offset += 2


def http1(address, port, sni, timeout, alpn=None):
    with tls_socket(address, port, sni, ["http/1.1"] if alpn is None else alpn, timeout) as stream:
        stream.sendall(("GET / HTTP/1.1\r\nHost: " + sni +
                        "\r\nAccept-Encoding: identity\r\nConnection: close\r\n\r\n").encode("ascii"))
        result = bytearray()
        while True:
            piece = stream.recv(16384)
            if not piece:
                break
            result.extend(piece)
            if len(result) > MAX_BODY:
                raise RuntimeError("HTTP response exceeded safety limit")
    head, separator, body = bytes(result).partition(b"\r\n\r\n")
    if not separator:
        raise RuntimeError("fallback did not return an HTTP response")
    first = head.split(b"\r\n", 1)[0].split()
    if len(first) < 2 or first[0] not in (b"HTTP/1.0", b"HTTP/1.1"):
        raise RuntimeError("invalid fallback HTTP status line")
    status = int(first[1])
    headers = {}
    for line in head.split(b"\r\n")[1:]:
        name, delimiter, value = line.partition(b":")
        if delimiter:
            headers[name.strip().lower()] = value.strip().lower()
    if b"chunked" in headers.get(b"transfer-encoding", b""):
        body = dechunk(body)
    if headers.get(b"content-encoding", b"identity") != b"identity":
        raise RuntimeError("fallback ignored identity content encoding")
    return status, body


def h2_frame(kind, flags, stream_id, data=b""):
    return len(data).to_bytes(3, "big") + bytes([kind, flags]) + struct.pack("!I", stream_id) + data


def hpack_integer(block, offset, bits):
    mask = (1 << bits) - 1
    value = block[offset] & mask
    offset += 1
    if value < mask:
        return value, offset
    shift = 0
    while offset < len(block):
        byte = block[offset]
        offset += 1
        value += (byte & 127) << shift
        if byte < 128:
            return value, offset
        shift += 7
        if shift > 56:
            break
    raise RuntimeError("invalid HPACK integer")


def hpack_string(block, offset):
    huffman = bool(block[offset] & 128)
    length, offset = hpack_integer(block, offset, 7)
    end = offset + length
    if end > len(block):
        raise RuntimeError("incomplete HPACK string")
    value = None if huffman else block[offset:end].decode("ascii")
    return value, end


def hpack_status(block):
    # Nginx uses the static HPACK :status entries; other headers may be Huffman
    # encoded and are skipped, not decoded. No third-party HTTP/2 dependency.
    static = {8: "200", 9: "204", 10: "206", 11: "304", 12: "400", 13: "404", 14: "500"}
    offset = 0
    while offset < len(block):
        byte = block[offset]
        if byte & 128:
            index, offset = hpack_integer(block, offset, 7)
            if index in static:
                return int(static[index])
            continue
        if byte & 224 == 32:
            _, offset = hpack_integer(block, offset, 5)
            continue
        index, offset = hpack_integer(block, offset, 6 if byte & 64 else 4)
        name = None
        if index == 0:
            name, offset = hpack_string(block, offset)
        value, offset = hpack_string(block, offset)
        if (index in static or name == ":status") and value is not None:
            return int(value)
    return None


def http2(address, port, sni, timeout):
    with tls_socket(address, port, sni, ["h2"], timeout) as stream:
        if stream.selected_alpn_protocol() != "h2":
            raise RuntimeError("server did not negotiate browser HTTP/2")
        authority = sni.encode("ascii")
        if len(authority) > 126:
            raise RuntimeError("HTTP/2 authority exceeds probe limit")
        headers = b"\x82\x87\x84\x01" + bytes([len(authority)]) + authority
        stream.sendall(b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n" +
                       h2_frame(4, 0, 0) + h2_frame(1, 5, 1, headers))
        status = None
        body = bytearray()
        header_block = bytearray()
        done = False
        while not done:
            header = exact(stream, 9)
            length = int.from_bytes(header[:3], "big")
            kind, flags = header[3], header[4]
            stream_id = int.from_bytes(header[5:], "big") & 0x7fffffff
            if length > MAX_BODY:
                raise RuntimeError("HTTP/2 frame exceeded safety limit")
            data = exact(stream, length)
            if kind == 4 and not flags & 1:
                stream.sendall(h2_frame(4, 1, 0))
            elif kind == 6 and not flags & 1:
                stream.sendall(h2_frame(6, 1, 0, data))
            elif kind in (1, 9) and stream_id == 1:
                padding = data[0] if kind == 1 and flags & 8 else 0
                start = int(kind == 1 and bool(flags & 8)) + (5 if kind == 1 and flags & 32 else 0)
                header_block.extend(data[start:len(data) - padding] if padding else data[start:])
                if flags & 4:
                    decoded = hpack_status(bytes(header_block))
                    if decoded is not None:
                        status = decoded
                    header_block.clear()
                done = bool(flags & 1)
            elif kind == 0 and stream_id == 1:
                padding = data[0] if flags & 8 else 0
                content = data[1:len(data) - padding] if flags & 8 else data
                body.extend(content)
                if len(body) > MAX_BODY:
                    raise RuntimeError("HTTP/2 body exceeded safety limit")
                if length and not flags & 1:
                    increment = struct.pack("!I", length)
                    stream.sendall(h2_frame(8, 0, 0, increment) + h2_frame(8, 0, 1, increment))
                done = bool(flags & 1)
            elif kind in (3, 7):
                raise RuntimeError("HTTP/2 fallback reset/closed stream before body completed")
        if status is None:
            raise RuntimeError("HTTP/2 :status could not be decoded")
        return status, bytes(body)


def vless_header(identity, destination_port):
    return (b"\x00" + uuid.UUID(identity).bytes + b"\x00\x01" +
            destination_port.to_bytes(2, "big") + b"\x01\x7f\x00\x00\x01")


def vless_response(stream):
    response = exact(stream, 2)
    if response[0] != 0:
        raise RuntimeError("not a VLESS response (possibly misrouted to website)")
    exact(stream, response[1])


def check_body(status, body, reference, marker):
    if status != 200:
        raise RuntimeError("browser website HTTP status was " + str(status) + ", expected 200")
    if not body:
        raise RuntimeError("browser website returned an empty body")
    if marker:
        if marker.encode("utf-8") not in body:
            raise RuntimeError("browser website missing expected marker")
    reference_match = "not_checked"
    if marker:
        reference_match = "explicit_marker"
    elif reference is not None:
        if body == reference:
            reference_match = "exact_body"
        else:
            # The existing site produces per-Host/per-request fields. Require
            # its stable HTML title instead of silently claiming a byte match.
            pattern = rb"<title[^>]*>(.*?)</title>"
            expected = re.search(pattern, reference, re.I | re.S)
            actual = re.search(pattern, body, re.I | re.S)
            if not expected or not actual or expected.group(1) != actual.group(1):
                raise RuntimeError("fallback website differs from unchanged reference site; "
                                   "use --expected-marker for a dynamic website")
            reference_match = "stable_html_title"
    return {"http_status": status, "bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
            "reference_match": reference_match}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--address", default="203.0.113.10")
    parser.add_argument("--port", type=int, default=443)
    parser.add_argument("--timeout", type=float, default=15)
    parser.add_argument("--http2", action="store_true", help="also test browser HTTP/2")
    parser.add_argument("--xray-only", action="store_true",
                        help="expect standard Xray; report legacy header-only incompatibility without requiring it")
    parser.add_argument("--relay-aliases", action="store_true",
                        help="also verify legacy relay destinations 443 and 8443 map to hbbr")
    parser.add_argument("--legacy-order", action="store_true",
                        help="require exact [0,0] response before EVERY RustDesk registration/relay payload")
    parser.add_argument("--sni", help="override TLS SNI, otherwise read TLS profile")
    parser.add_argument("--reference-address", default="203.0.113.10")
    parser.add_argument("--reference-port", type=int, default=443)
    parser.add_argument("--reference-sni", default="example.com")
    parser.add_argument("--expected-marker", help="body marker instead of an exact reference-body comparison")
    parser.add_argument("--skip-reference", action="store_true")
    args = parser.parse_args()
    profile = json.loads(args.profile.read_text(encoding="utf-8-sig"))
    params = profile["vless"]["tls_profile"]
    identity = params["uuid"]
    sni = args.sni or params["server_name"]
    uuid.UUID(identity)
    results = []

    def run(name, operation):
        try:
            details = operation() or {}
            result = {"test": name, "pass": True, **details}
        except Exception as error:
            # No raw responses or configuration values are included in errors.
            result = {"test": name, "pass": False, "error": str(error)}
        results.append(result)
        return result

    reference = None
    if not args.skip_reference and not args.expected_marker:
        try:
            status, reference = http1(args.reference_address, args.reference_port,
                                      args.reference_sni, args.timeout)
            if status != 200:
                raise RuntimeError("reference website did not return HTTP 200")
            results.append({"test": "unchanged reference website", "pass": True,
                            "bytes": len(reference), "sha256": hashlib.sha256(reference).hexdigest()})
        except Exception as error:
            print(json.dumps({"pass": False, "results": [{"test": "unchanged reference website", "pass": False,
                                                          "error": str(error)}]}, indent=2))
            return 1

    def browser(operation):
        status, body = operation(args.address, args.port, sni, args.timeout)
        return check_body(status, body, reference, args.expected_marker)

    run("browser HTTP/1.1 fallback", lambda: browser(http1))
    run("browser without ALPN fallback", lambda: browser(
        lambda address, port, sni, timeout: http1(address, port, sni, timeout, alpn=[])))
    if args.http2:
        run("browser HTTP/2 fallback", lambda: browser(http2))

    def legacy_header_only():
        # Old hbvless clients wait for [0,0] before sending RustDesk data.
        # Stock Xray may wait for backend data before emitting this header,
        # causing a deadlock for hbbs/hbbr. Do not mask that with a first packet.
        with tls_socket(args.address, args.port, sni, [], args.timeout) as stream:
            stream.settimeout(min(3, args.timeout))
            stream.sendall(vless_header(identity, 21116))
            try:
                vless_response(stream)
            except TimeoutError as error:
                raise RuntimeError("header-only client deadlock: no VLESS response before RustDesk payload") from error
        return {"response_before_payload": True}

    legacy = run("legacy client header-only compatibility", legacy_header_only)

    def send_request(stream, destination, payload):
        if args.legacy_order:
            stream.sendall(vless_header(identity, destination))
            if exact(stream, 2) != b"\x00\x00":
                raise RuntimeError("old client requires an immediate exact [0,0] VLESS response")
            stream.sendall(payload)
        else:
            stream.sendall(vless_header(identity, destination) + payload)

    def registration(destination, alpn):
        with tls_socket(args.address, args.port, sni, alpn, args.timeout) as stream:
            send_request(stream, destination, frame(bytes.fromhex("a20100")))
            if not args.legacy_order:
                vless_response(stream)
            if not recv_frame(stream).startswith(bytes.fromhex("aa01")):
                raise RuntimeError("registration backend did not answer RustDesk TestNat")
        return {"backend_port": destination}

    for alpn in ([], ["http/1.1"], ["h2"]):
        label = alpn[0] if alpn else "none"
        for destination in (21115, 21116):
            run("VLESS ALPN " + label + " registration " + str(destination),
                lambda destination=destination, alpn=alpn: registration(destination, alpn))

    def relay(destination=21117):
        pairing = str(uuid.uuid4())
        request = protobuf_text(1, "deployment-probe") + protobuf_text(2, pairing)
        payload = protobuf_varint((18 << 3) | 2) + protobuf_varint(len(request)) + request
        with tls_socket(args.address, args.port, sni, [], args.timeout) as first:
            send_request(first, destination, frame(payload))
            time.sleep(0.15)
            with tls_socket(args.address, args.port, sni, ["http/1.1"], args.timeout) as second:
                send_request(second, destination, frame(payload))
                sample = b"RustDesk-VLESS-TLS-Fallback-" * 2600
                time.sleep(0.2)
                first.sendall(sample)
                if not args.legacy_order:
                    vless_response(second)
                if exact(second, len(sample)) != sample:
                    raise RuntimeError("relay data corrupted first to second")
                second.sendall(sample)
                if not args.legacy_order:
                    vless_response(first)
                if exact(first, len(sample)) != sample:
                    raise RuntimeError("relay data corrupted second to first")
        return {"logical_destination_port": destination, "bytes_each_way": len(sample)}

    for destination in ([21117, 443, 8443] if args.relay_aliases else [21117]):
        run("VLESS paired bidirectional relay " + str(destination),
            lambda destination=destination: relay(destination))

    def denied():
        with tls_socket(args.address, args.port, sni, [], args.timeout) as stream:
            stream.sendall(vless_header(identity, 22) + b"SSH-2.0-deployment-probe\r\n")
            deadline = time.monotonic() + min(3, args.timeout)
            response = bytearray()
            header_length = None
            while time.monotonic() < deadline:
                stream.settimeout(max(0.01, deadline - time.monotonic()))
                try:
                    piece = stream.recv(512)
                except (TimeoutError, ConnectionResetError):
                    break
                if not piece:
                    break
                response.extend(piece)
                if response[0] != 0:
                    raise RuntimeError("authenticated forbidden destination returned non-VLESS data")
                if len(response) >= 2:
                    header_length = 2 + response[1]
                    if len(response) > header_length:
                        raise RuntimeError("authenticated forbidden SSH destination returned backend data")
            if response and (header_length is None or len(response) != header_length):
                raise RuntimeError("forbidden destination returned an incomplete VLESS response header")
        return {"backend_port": 22, "vless_header_received": bool(response), "backend_bytes": 0}

    run("authenticated RustDesk UUID cannot proxy SSH 22", denied)

    def invalid():
        with tls_socket(args.address, args.port, sni, ["http/1.1"], args.timeout) as stream:
            stream.sendall(vless_header(str(uuid.uuid4()), 22) +
                           b"GET / HTTP/1.1\r\nHost: probe.invalid\r\nConnection: close\r\n\r\n")
            stream.settimeout(min(4, args.timeout))
            try:
                response = stream.recv(512)
            except (TimeoutError, ConnectionResetError):
                response = b""
            if response and not response.startswith((b"HTTP/1.1 ", b"HTTP/1.0 ")):
                raise RuntimeError("invalid UUID unexpectedly returned non-HTTP backend data")
        return {"website_rejected_invalid_bytes": bool(response)}

    run("invalid UUID never reaches SSH/backend", invalid)
    passed = all(result["pass"] for result in results)
    business_pass = all(result["pass"] for result in results if result is not legacy)
    if args.xray_only:
        passed = business_pass
    print(json.dumps({"pass": passed, "business_pass": business_pass,
                      "mode": "xray-only" if args.xray_only else "require-legacy-compatible",
                      "legacy_client_compatibility": legacy["pass"],
                      "legacy_order_for_all_sessions": args.legacy_order,
                      "address": args.address, "port": args.port,
                      "results": results}, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
