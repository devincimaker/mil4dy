# mil4dy

## Linear Integration

- **Workspace**: fioris
- **Team**: Mil4dy
- **Project URL**: https://linear.app/fioris/team/M4D/all
- **Issue Identifier**: M4D

## UI

Every UI we ship must work on **desktop and mobile**. This is not optional polish.

- Layout fills the viewport. `html`, `body`, `#root` (or equivalent), and the app shell are `width: 100%` / `height: 100%` (or `100dvh`). Do not let the shell shrink-wrap to a sidebar.
- Use an explicit grid or flex that assigns every region a cell (`grid-template-areas` or equivalent). Do not rely on implicit auto-placement for the main chrome.
- Desktop: usable side-by-side (crate | stage, or similar). Phone: stacked, still full width, no amputated features.
- Check both viewports before calling UI work done — a wide laptop window and a phone-width viewport (~390px). Exercise the flow, not just a screenshot.
- Touch targets stay usable on mobile. Text and controls must not overflow or sit in a skinny unused column next to empty space.

If a layout looks like a narrow bar with empty window beside it, it is broken. Fix the grid, do not add another breakpoint on top.
