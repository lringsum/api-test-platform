import socket
import sys
import urllib.error
import urllib.request


def probe_port(port: int) -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("127.0.0.1", port))
        return 0
    except OSError:
        return 2
    finally:
        sock.close()


def probe_url(url: str) -> int:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "api-test-platform-launcher"},
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            status = getattr(response, "status", response.getcode())
            return 3 if 200 <= int(status) < 500 else 2
    except urllib.error.HTTPError as exc:
        return 3 if 200 <= int(exc.code) < 500 else 2
    except Exception:
        return 2


def main() -> int:
    if len(sys.argv) < 2:
        return 1
    command = (sys.argv[1] or "").strip().lower()
    if command == "port":
        if len(sys.argv) < 3:
            return 1
        return probe_port(int(sys.argv[2]))
    if command == "url":
        if len(sys.argv) < 3:
            return 1
        return probe_url(sys.argv[2])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
