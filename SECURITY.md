# Security

## Supported versions

SKLib is pre-release. Security fixes currently target latest main branch.

## Reporting

Do not open public issue for suspected vulnerability. Contact maintainers
privately through repository security advisory when available.

## Deployment warning

Web editor can modify component files. It is designed to bind to
`127.0.0.1` and has no user authentication. Do not expose it to local network
or internet by using `--host 0.0.0.0` unless protected by suitable authenticated
reverse proxy and network controls.

Supplier credentials belong only in ignored `.env` or process environment.
Never commit them or supplier response dumps.
