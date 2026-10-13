# Development MinIO source builds

Public upstream MinIO/mc images no longer pull. Compose builds both binaries from
official repositories at immutable commits:

- Server: `7aac2a2c5b7c882e68c1ce017d8256be2feea27f`
- Client: `77f82e18b5401a65958f1619df6ebb994634bd88`

The Go module checksums are verified during compilation. Multi-stage builds keep
the compiler and source checkout out of runtime images; upstream licenses remain.
The first build downloads dependencies and compiles both binaries, so it takes
longer than pulling prebuilt images. Docker caches subsequent builds.

Run `docker compose up --build -d`, then `python scripts/docker_smoke.py`.
The smoke check uploads, reads and removes a unique object in the development bucket.
Existing volumes and objects are preserved.
The API waits for the bucket setup job to complete successfully. Compilation uses
one worker and a conservative Go memory budget. On the current Windows development
host, `%USERPROFILE%\.wslconfig` limits WSL memory to 4 GB after initial Docker
builds exhausted Windows virtual-memory capacity.

Upstream community repositories are archived and unmaintained. These source builds
restore local development; they do not establish production storage suitability.
Choose and review a maintained S3-compatible deployment/provider before production.
See [upstream server](https://github.com/minio/minio) and
[upstream client](https://github.com/minio/mc).
