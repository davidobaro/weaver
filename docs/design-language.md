# Workspace design language

Journal, For you, and People share `PageHeading` and the `.workspace-page` layout. New page introductions should use them rather than introduce page-specific padding or heading sizes.

## Reconciled differences

Measured at a 1200px desktop viewport before this pass:

| Element | Journal | For you | People | Shared rule |
| --- | --- | --- | --- | --- |
| Title top | 140px | 114px | 165px | 124px |
| Title left | 279px | 282px | 279px | 279px |
| Title font size | 32px | 32px | 39px | 32px |
| Introduction | Title and subtitle | Title and subtitle | Eyebrow, title, subtitle, vertical caption | Title and subtitle |
| Heading-to-content gap | 80px | 26px | 35px | 32px |
| Top-bar page label | Absent | Absent | Present | Present on every page |

People's About heading previously used a 23px serif treatment while Tasks & obligations and Your entries used small sans-serif labels. These now share a 12px, weight 600 section-label treatment. Entry filters and full-page suggestion filters share 11px text, padding, radius, and selected-state colors.

## Layout and type

- Desktop page inset: 48px from the top bar; 45px horizontal gutters, reducing to 30px and then 22px at smaller desktop/tablet widths.
- Mobile page inset: 32px from the top bar, 20px gutters.
- Page titles: Georgia, weight 400, 32px/1.2 on desktop and 29px/1.2 on mobile; 10px to the subtitle.
- Subtitles: DM Sans, 12px/1.6. Headings have a 32px bottom gap on desktop, 28px on mobile.
- Section labels: DM Sans, 12px/1.5, weight 600.
- Main page containers share a 1440px maximum width and alignment. For you keeps an 870px reading width inside that shared container, anchored to the same left gutter.
- The journal's For you heading stays level with its page title on desktop. Its compact cards, profile task controls, editorial writing field, and branding retain their purpose-specific sizes.

Checked Journal, For you, and People at 390px, 820px, 1200px, and 1600px widths. Title positions and sizes match between pages at each size; no document-level horizontal overflow appeared at 390px or 820px. Profile task strips intentionally scroll within their own containers.
