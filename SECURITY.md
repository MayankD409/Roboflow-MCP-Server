# Security Policy

## Supported versions

Only the latest minor release on `main` receives security fixes while the
project is pre-`1.0`. After `1.0`, the two most recent minors will be supported.

## Reporting a vulnerability

Please do not open a public issue for security problems. Instead, email the
maintainer at **deshpandemayank5@gmail.com** with:

- A description of the issue and its impact.
- Steps to reproduce or a proof of concept.
- Any suggested fix, if you have one.

You should get an acknowledgement within 72 hours. If the report is valid,
we will agree on a disclosure timeline before any public discussion.

## Handling secrets

This server requires a Roboflow private API key. Never commit it, never log it,
never paste it in issues. The server scrubs the key from logs and error output;
if you ever see a key leak through, report it as a vulnerability.
