from ipaddress import IPv4Address

import uvicorn
from api_manager_books.api.api import app
from api_manager_books.api.security.utils import ensure_self_signed_cert

def main():
    cert_file, key_file = ensure_self_signed_cert("cert.pem", "key.pem",
                                                  common_name="localhost",
                                                  ip_address=IPv4Address("127.0.0.1"))
    uvicorn.run(
        app,
        host='0.0.0.0',
        port=1408,
        reload=False,
        ssl_certfile=cert_file,
        ssl_keyfile=key_file,
    )


if __name__ == '__main__':
    main()


