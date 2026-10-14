# CloudVault development storage relocation

Destination: D:\CloudVault-Dev. Project target: D:\CloudVault-Dev\Project\CloudVault.

Machine-local migration scripts and private backups are kept outside Git under D:\CloudVault-Dev\Migration. They preserve existing C: paths with NTFS directory junctions, verify file counts/sizes/SHA-256 before deleting old copies, and refuse unexpected destinations or links. Docker's stopped disk image includes PostgreSQL, uploaded objects, images and build cache; the original is retained until runtime checks pass. Codex live databases/runtime require closing the app before their migration.

The repository includes uncommitted Phases 4–6 and the visual redesign; migration must preserve hidden Git files, .env, ignored database backups and installed dependencies. App installers managed by Windows require a separate supported relocation or administrator operation; do not manually move WindowsApps files.

Use the D: project path for new terminals. Existing project paths remain compatibility junctions after migration. Do not delete either junction target or treat D: as a backup disk: it remains the live working copy.

Current verification: Docker WSL storage and npm/pip/Playwright caches have completed. Docker Compose, UI/API, private bucket, mc and application-adapter round trips pass. C: free increased from 29.9 to 41.8 GiB. Project copy passed 16,529 file checks plus Git-state comparison, but its original directory remains open in this chat; final cutover is deferred until complete Codex exit.

The administrator finalizer is running and waiting. Its result is in D:\CloudVault-Dev\Migration\STATUS.txt and finish.log. Windows Package Manager controls the Codex installed-app move and may require D:\WindowsApps/WpSystem. If any stage cannot proceed, its original remains and STATUS names the pending stage. Fully quit Codex and keep it closed until a final result is recorded. A desktop shortcut opens the development folder.
