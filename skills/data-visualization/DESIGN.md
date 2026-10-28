# Data Observatory design contract

The audience is a curious analyst exploring evidence, comparing cohorts, and understanding change. The artifact is an analytical workspace, not a marketing page. Its objects are datasets, observations, fields, views, a cohort, an observed time cursor, selected entities, and saved questions.

The systems-drawing sibling relationship is structural: an agent authors a declarative document; an engine renders it; a verifier checks the result; a portable HTML artifact works without a service. Three-dimensional solids and monochrome restrictions do not transfer to quantitative charts. Use position and length before area, meaningful category colors, fixed domains during playback, explicit units, and visible sources.

The visual reference is an editorial statistical atlas: warm neutral page, a large white plotting surface, dark ink, fine rules, serif question headings, and compact sans-serif controls. One dark green accent identifies active controls. Data colors come from a fixed accessible palette. Color never carries identity alone: labels, shapes or detail inspection also expose it. No gradients, shadows, decorative icons, floating cards, or ornamental KPI tiles.

The signature interaction is the shared observed-time controller. Scrubbing or playing updates all linked views and rows; selection preserves entity identity across frames. A selected mark opens its record alongside the chart. An optional two-dimensional brush defines the cohort. Comparison uses visible counts and fixed axes; it does not conceal excluded observations. Source caveats remain visible below the title and source details are one action away.

The main view gets the largest area. Supporting information sits in a narrow right column on wide screens and below the chart on phones. The hierarchy is title, question, plot, controls, then methodological detail. Tabs choose a view; chart/data/source tabs change presentation of the same cohort. The saved questions are short, inspectable state changes. There is no simulated AI chat.

Tokens live only in assets/style.css. Minimum touch target is 36px (44px on compact screens), focus outlines are visible, controls have text labels, tables provide keyboard access to every mark, and reduced motion disables automatic playback. The runtime is scoped to its own Shadow DOM, owns its event handlers and timer, and can be disposed without affecting another instance.

Decision record, 2026-10-28: use Observable Plot and D3 as pinned local rendering dependencies; build original interaction, provenance, and authoring contracts around them. Prefer observed-frame playback over synthetic interpolated measurements. Allow future renderers through an explicit registry without forcing the agent into a catalog of predetermined questions.

Screenshot review, 2026-10-28: keep time controls above the plot and sticky during long comparisons; show the observed date or range beside each chart title. Retain all transport directions on mobile, wrap view choices, label full-width filters, and provide a touch-accessible comparison mode. Full-history views, tables, exports and counts share the same rows; clicking an old observation opens that exact time. Dense unselected trajectories are gray; chosen entities receive color and endpoint labels. Remove duplicate observation/entity counters when they add no information.
