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

Phase 5 setup explicitly sets anonymous bucket access to none. Compose passes the
complete S3 endpoint/credential/bucket/region configuration to backend and dispatcher.
The application adapter uses Signature V4 and UUID-only scoped keys. Docker smoke
checks anonymous listing denial and runs `app.jobs.check_storage` for an actual
put/head/bounded-read/delete round trip with cleanup. Integration tests create their
own uniquely named disposable buckets; they do not clear the application bucket.

Phase 6 adds MINIO_API_CORS_ALLOW_ORIGIN for localhost app/development and the
127.0.0.1 disposable browser origin. API uses the internal endpoint for HEAD and
S3_PUBLIC_ENDPOINT for browser signatures; both target the same bucket. Browser
PUT binds size, SHA-256, generic content type and If-None-Match. Public GET/list
remains denied. Provider checksum/conditional support is tested on this local build;
production S3/R2 needs its own compatibility and IAM/CORS verification.
