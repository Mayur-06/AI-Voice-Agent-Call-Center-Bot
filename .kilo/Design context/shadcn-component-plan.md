# Aura Voice Studio — shadcn/ui Component Plan

Companion to `Aura_Voice_Studio_UI_Design_Plan_updated.docx`. Maps each shadcn
component to the screens, sections, and internal components defined in that
plan (see section 7, "Shared Component Architecture").

---

## 1. Button
`npx shadcn@latest add button`

**Used in**
- Screen 01 (Session Setup): "Start Call" primary CTA — Ink Black fill, Ghost White text
- Screen 01: "Test microphone" secondary action
- Screen 02 (Live Call): CallControls — icon-variant buttons (mic, pause)
- Screen 03 (Post-Call): playback controls, "New Session"
- Navigation: BackNavigation — ghost variant

**Notes**
- Map `default` variant → Ink Black fill / Ghost White text (primary CTA rule from plan section 3)
- Map `ghost`/`outline` variants → secondary actions, avoid competing with Start Call / End Call
- End Call button should use a distinct destructive styling, kept visually separated from mic controls per section 4

---

## 2. Card
`npx shadcn@latest add card`

**Composition**
```
Card
├── CardHeader
│   ├── CardTitle
│   ├── CardDescription
│   └── CardAction
├── CardContent
└── CardFooter
```

**Used in**
- MetricCard (Screen 04 KPI strip, Screen 03 Call Metrics)
- PersonaCard (Screen 01 — Advisors & Specialists grid)
- VoiceCard (Screen 01 — Voice Style: Aura, Echo, Orion)
- ContextCard (Screen 02 — Session Context panel)
- SummaryCard (Screen 03 — Key Takeaways & Agreed Decisions)
- FileAttachment (Screen 01 — compact card variant for uploaded reference files)

**Notes**
- Selected PersonaCard/VoiceCard state uses Pearl Beige background + check indicator (plan section 3 rule)
- CardAction slot fits the "Preview Voice" play button on VoiceCard

---

## 3. Avatar
`npx shadcn@latest add avatar`

**Composition**
```
Avatar / AvatarGroup
├── AvatarImage
├── AvatarFallback
└── AvatarBadge
```

**Used in**
- PersonaCard (Screen 01) — advisor portrait, AvatarFallback for initials if no image
- TranscriptMessage (Screen 02, Screen 03) — speaker identity next to each turn
- AvatarBadge — pairs with ConnectionIndicator/SpeakingIndicator to show active speaker

---

## 4. Toggle
`npx shadcn@latest add toggle`

**Used in**
- CallControls (Screen 02) — mute/unmute mic toggle
- CallControls (Screen 02) — pause affordance

**Notes**
- Pressed state should reduce visual intensity per the "Muted/disconnected: reduced visual intensity" rule (plan section 4)

---

## 5. Badge
`npx shadcn@latest add badge`

**Used in**
- ConnectionIndicator (Screen 02 top bar) — connection state label
- SpeakingIndicator (Screen 02, Screen 03) — "Aura is speaking..." / active turn marker
- SessionStatus (AppHeader, all screens)
- File count / attachment count on Selected Partner Summary (Screen 01)
- Sentiment labels (Screen 03 timeline markers, Screen 04 Sentiment Breakdown: Positive / Neutral / Friction)

---

## 6. Tooltip
`npx shadcn@latest add tooltip`

**Composition**
```
Tooltip
├── TooltipTrigger
└── TooltipContent
```

**Used in**
- ConnectionIndicator (Screen 02) — connection detail on hover
- Analytics KPI strip (Screen 04) — metric definitions (e.g. P95 latency, Efficiency)
- Icon-only CallControls buttons — accessible labels on hover

---

## 7. Chart (LineChart)
`npx shadcn@latest add chart` (installs the Recharts wrapper: `ChartContainer`, `ChartTooltip`, `ChartTooltipContent`)

**Used in**
- Daily Conversation Volume (Screen 04) — direct sessions vs. relay fallbacks
- Sentiment & Engagement Flow (Screen 03) — timeline markers (Intro, Latency Clarification, etc.)
- Sentiment Breakdown (Screen 04) — 30-day index
- Turn Latency & Stream Jitter (Screen 04) — edge handshake, relay buffer, SLA/target markers

**Reference implementation**
```tsx
"use client"
import { TrendingUp } from "lucide-react"
import { CartesianGrid, Line, LineChart, XAxis } from "recharts"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"

export const description = "A line chart"

const chartData = [
  { month: "January", desktop: 186 },
  { month: "February", desktop: 305 },
  { month: "March", desktop: 237 },
  { month: "April", desktop: 73 },
  { month: "May", desktop: 209 },
  { month: "June", desktop: 214 },
]

const chartConfig = {
  desktop: {
    label: "Desktop",
    color: "var(--chart-1)",
  },
} satisfies ChartConfig

export function ChartLineDefault() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Line Chart</CardTitle>
        <CardDescription>January - June 2024</CardDescription>
      </CardHeader>
      <CardContent>
        <ChartContainer config={chartConfig}>
          <LineChart
            accessibilityLayer
            data={chartData}
            margin={{ left: 12, right: 12 }}
          >
            <CartesianGrid vertical={false} />
            <XAxis
              dataKey="month"
              tickLine={false}
              axisLine={false}
              tickMargin={8}
              tickFormatter={(value) => value.slice(0, 3)}
            />
            <ChartTooltip
              cursor={false}
              content={<ChartTooltipContent hideLabel />}
            />
            <Line
              dataKey="desktop"
              type="natural"
              stroke="var(--color-desktop)"
              strokeWidth={2}
              dot={false}
            />
          </LineChart>
        </ChartContainer>
      </CardContent>
      <CardFooter className="flex-col items-start gap-2 text-sm">
        <div className="flex gap-2 leading-none font-medium">
          Trending up by 5.2% this month <TrendingUp className="h-4 w-4" />
        </div>
        <div className="leading-none text-muted-foreground">
          Showing total visitors for the last 6 months
        </div>
      </CardFooter>
    </Card>
  )
}
```

**Notes**
- Map `--chart-1` etc. to the palette tokens (Ink Black / Pearl Beige) rather than default shadcn chart colors, to satisfy "no decorative gradients or excessive legends" rule (plan section 6)
- SentimentChart, BarChart, LatencyChart reuse this same base pattern with different `dataKey`/`chartConfig`

---

## 8. Table
`npx shadcn@latest add table`

**Composition**
```
Table
├── TableCaption
├── TableHeader
│   └── TableRow
│       ├── TableHead (x N)
├── TableBody
│   └── TableRow
│       ├── TableCell (x N)
└── TableFooter
```

**Used in**
- PerformanceTable (Screen 04 — Agent & Persona Performance Registry: persona, model/deployment, region, session count, duration, sentiment alignment, P95 latency, handoff success)

**Notes**
- Must preserve column alignment for model/version and region metadata per plan section 6
- Pair with Pagination component below for table navigation

---

## 9. Dropdown Menu
`npx shadcn@latest add dropdown-menu`

**Composition**
```
DropdownMenu
├── DropdownMenuTrigger
└── DropdownMenuContent
    └── DropdownMenuGroup
        ├── DropdownMenuLabel
        ├── DropdownMenuItem
        └── DropdownMenuItem
```

**Used in**
- ExportMenu (Screen 03) — TXT Transcript, PDF Summary, MP3 Full Audio, Copy JSON Content

**Notes**
- Plan section 5 specifies these four export types must live inside one compact menu, not persistent toolbar buttons — this is exactly that pattern
- Simple `DropdownMenuGroup` + `DropdownMenuItem` list is sufficient; radio/checkbox/sub-menu variants are not needed here

---

## 10. Toggle Group
`npx shadcn@latest add toggle-group`

**Composition**
```
ToggleGroup
├── ToggleGroupItem
└── ToggleGroupItem
```

**Used in**
- Screen 01 — Voice Style selector (Aura / Echo / Orion) as a single-select group, alternative to individual VoiceCards if a more compact selector is needed
- Screen 04 — time-range filters on charts (e.g. 7d / 30d), if added later

---

## 11. Separator
`npx shadcn@latest add separator`

**Used in**
- ContextCard (Screen 02) — dividing persona summary / referenced files / audio state sections
- Screen 04 — dividing KPI strip from behavior charts, and charts from the operational table (per the four-level hierarchy in plan section 6)
- Screen 01 — dividing Conversation Partner / Voice Style / Reference Notes sections

---

## 12. Pagination
`npx shadcn@latest add pagination`

**Composition**
```
Pagination
└── PaginationContent
    ├── PaginationItem → PaginationPrevious
    ├── PaginationItem → PaginationLink
    ├── PaginationItem → PaginationEllipsis
    └── PaginationItem → PaginationNext
```

**Used in**
- PerformanceTable (Screen 04) — "Previous / Next" table navigation explicitly listed in plan section 6

---

## 13. Alert Dialog
`npx shadcn@latest add alert-dialog`

**Composition**
```
AlertDialog
├── AlertDialogTrigger
└── AlertDialogContent
    ├── AlertDialogHeader
    │   ├── AlertDialogMedia
    │   ├── AlertDialogTitle
    │   └── AlertDialogDescription
    └── AlertDialogFooter
        ├── AlertDialogCancel
        └── AlertDialogAction
```

**Used in**
- Screen 02 — End Call confirmation (destructive action, kept visually separated from mic controls per plan section 4)
- Screen 01 — confirming removal of an attached reference file (optional, if destructive-enough to warrant confirmation)

---

## Screen-to-Component Matrix

| Screen | Components used |
|---|---|
| 01 — Session Setup | Card, Avatar, Badge, Button, ToggleGroup, Separator, AlertDialog (file remove) |
| 02 — Live Voice Call | Button, Toggle, Badge, Tooltip, Card, Avatar, Separator, AlertDialog (End Call) |
| 03 — Post-Call / Debrief | Card, Chart, Badge, Avatar, DropdownMenu (Export), Button |
| 04 — Analytics & Performance | Card, Chart, Table, Pagination, Tooltip, Separator, Badge |

---

## Component Pairing Guidelines

Components that must be composed together, and the rule governing that composition.

**Card + Chart**
- LineChart/SentimentChart/TopicChart/LatencyChart always render inside a Card (CardHeader for title/description, CardContent for the chart, CardFooter for trend/summary text) — never a bare chart on the canvas
- Keeps charts visually consistent with MetricCard/SummaryCard elevation and radius (plan section 2.3 radius scale)

**Card + Avatar + Badge**
- PersonaCard = Card wrapping Avatar (portrait) + Badge (selected/check indicator)
- Selected state = Pearl Beige Card background + Badge check indicator together, never one without the other (plan section 3 rule)

**Table + Pagination**
- PerformanceTable (Screen 04) always pairs with Pagination directly below it — Previous/Next must control the same data source as the table body
- Pagination should sit outside the Table component, in the same Card/section container, not inside TableFooter

**Button + Tooltip**
- Any icon-only Button (CallControls: mic, pause) must be wrapped in Tooltip with TooltipTrigger — icon-only controls are not allowed without an accessible label
- Text-labeled Buttons (Start Call, Export) do not need Tooltip

**Button + AlertDialog**
- End Call Button is always the AlertDialogTrigger, never a direct action — confirmation is mandatory per plan section 4 ("must remain visually separated from microphone controls")
- File-remove Button (Screen 01) follows the same pattern if confirmation is enabled

**Button + DropdownMenu**
- ExportMenu = single Button ("Export") as DropdownMenuTrigger, containing the four export DropdownMenuItems — never four separate Buttons in the toolbar (plan section 5, explicit rule)

**Toggle + Badge**
- Mic mute Toggle should update the adjacent ConnectionIndicator/SpeakingIndicator Badge in the same state change — muting must visibly reduce indicator intensity together, not independently (plan section 4)

**Separator + Card groups**
- Separator is only used between sibling sections inside a Card or panel (e.g. ContextCard's persona/files/audio sections) — not between unrelated top-level page sections, where spacing-scale gaps are used instead (plan section 2.3)

**ToggleGroup + Separator**
- If Voice Style uses ToggleGroup instead of individual VoiceCards, wrap it with Separator above/below to match the section-dividing pattern used elsewhere on Screen 01

---

## Install All (single pass)

```bash
npx shadcn@latest add button card avatar toggle badge tooltip chart table dropdown-menu toggle-group separator pagination alert-dialog
```
