# Next.js Frontend Validation Checklist

Use this checklist to validate the Next.js frontend against expected product behavior.

## Chat Flow
- [ ] Start a new chat and send a prompt.
- [ ] Confirm assistant response streams token-by-token.
- [ ] Confirm `session_id` is assigned after first response.
- [ ] Open an older session and verify historical messages load instantly.
- [ ] Continue a historical session and verify it appends to the same session.

## Session History
- [ ] New sessions appear in the history list after response completion.
- [ ] Active session is visibly highlighted.
- [ ] Switching sessions does not trigger full-page reload.

## Document Management
- [ ] Upload `.pdf`, `.docx`, and `.html` files successfully.
- [ ] Uploaded files appear in documents list with timestamp.
- [ ] Deleting a document removes it from UI and backend.
- [ ] Unsupported file types return clear backend error message.

## Responsiveness
- [ ] Desktop layout renders as history | chat | docs panels.
- [ ] Mobile layout hides side panels and uses History/Docs drawers.
- [ ] Chat area scrolls to the latest message during streaming.

## Failure Paths
- [ ] Stop backend and verify frontend shows actionable error toasts.
- [ ] Simulate upload failure and verify button recovery state.
- [ ] Simulate stream failure and verify fallback assistant error message.
