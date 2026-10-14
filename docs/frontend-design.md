# Frontend design pass — 2026-10-14

CloudVault now has a shared workspace shell and consistent visual language. The previous disconnected form pages were replaced with persistent workspace navigation, a welcoming overview, a split sign-in/register layout, and a clearer content browser.

Changed components: AppShell, AuthLayout, Icon, HomePage, LoginPage, RegisterPage, recovery/account-action/invitation layouts, FoldersPage, FileList and UploadForm. Shared styles live in frontend/src/index.css. Workspace settings and account security inherit the shell and control styling.

Navigation highlights the active route. Mobile navigation preserves account actions. Folder icons and file status badges distinguish content, and upload/empty/error states explain actual behavior. No placeholder search, storage totals, download controls or AI features were added. Existing permission, tenant isolation, session invalidation and upload integrity logic remain unchanged.

Verification uses existing frontend tests and a new e2e/design.pw.ts journey against a disposable database, SMTP inbox and storage bucket. It registers/verifies a real test identity, creates folders, checks desktop/mobile navigation, signs out, checks horizontal overflow and captures screenshots in ignored .local/design. The upload journey continues to exercise a real presigned PUT.

Decision: ADR-023. Phase 7 has not started. No new database migration is required. This is a visual foundation, with broader accessibility and future-feature UX review still needed as development progresses.

Verified: 39 frontend tests and 13 Chromium/SMTP/real-storage journeys pass, including the new desktop/mobile checks; ESLint, TypeScript/Vite build and whitespace checks pass. The local Docker frontend was rebuilt successfully. Initial Chromium startup crashes were rerun; an interrupted disposable bucket was cleaned using the manifest guard. No application data was cleared.
