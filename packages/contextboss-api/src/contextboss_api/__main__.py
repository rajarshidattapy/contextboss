import argparse


def main() -> None:
    import uvicorn

    from .app import create_app

    p = argparse.ArgumentParser(prog="contextboss-api")
    p.add_argument("--host", default="127.0.0.1",
                   help="default localhost; expose remotely only behind HTTPS with API keys")
    p.add_argument("--port", type=int, default=8788)
    args = p.parse_args()
    uvicorn.run(create_app(), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
