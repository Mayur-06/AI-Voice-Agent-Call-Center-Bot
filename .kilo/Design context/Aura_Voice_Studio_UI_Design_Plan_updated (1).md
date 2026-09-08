**AURA VOICE STUDIO  /  UI DESIGN PLAN** 

##### **AURA VOICE STUDIO** 

# **UI Design & Pixel-Perfection Plan** 

_Four-screen voice intelligence experience_ 

###### **INK BLACK #03191e    PEARL BEIGE #ebe1c1    GHOST WHITE #fbfbff** 

Purpose: define the visual system, information hierarchy, component behavior, and implementation rules required to reproduce the supplied reference screens with a consistent, production-ready UI. 

## **1. Product UI Direction** 

The four supplied designs should be implemented as one cohesive product, not as four independent pages. The visual language is premium, minimal, calm, and data-aware. The experience should move naturally through Prepare → Talk → Understand → Improve. 

- Prepare — Session setup and configuration 

- Talk — Live voice conversation and presence 

- Understand — Post-call replay, transcript, and decisions 

- Improve — Analytics, latency, sentiment, and persona performance 

## **2. Core Design System** 

### **2.1 Color Tokens** 

|**Token**|**Hex**|**Primary use**|**Usage rule**|
|---|---|---|---|
|Ink Black|#03191e|Primary text, icons,<br>controls, charts|Default high-contrast UI<br>color|
|Pearl Beige|#ebe1c1|Accent, selected states,<br>ambient highlights|Use sparingly; never let it<br>overpower content|
|Ghost White|#fbfbf|Main canvas, light surfaces|Base background and<br>spacious breathing room|



### **2.2 Typography** 

Primary typeface: Montserrat. Use a clean weight hierarchy rather than many font families. 

|**Role**|**Size**<br>**Weight**<br>**Notes**|
|---|---|



Page 1 

**AURA VOICE STUDIO  /  UI DESIGN PLAN** 

|Display|32–40 px|600–700|Hero / central title|
|---|---|---|---|
|Page title|24–28 px|600–700|Primary screen heading|
|Section title|16–18 px|600|Card and module headings|
|Body|14–15 px|400–500|Descriptions, transcript,<br>helper copy|
|Metadata|11–12 px|500|Timestamps, statuses,<br>secondary labels|
|Metrics|24–32 px|600–700|KPIs and headline<br>measurements|



Technical/code-like data may use JetBrains Mono where already established by the supplied post-call reference, especially for structured export or technical content. 

### **2.3 Layout Tokens** 

- Desktop content max width: 1440 px 

- Page padding: 32–48 px on desktop 

- 12-column grid with 20–24 px gutters 

- Spacing scale: 4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48 / 64 / 80 px 

- Radius scale: 8 / 12 / 16 / 24 px + pill 999 px 

- Borders: rgba(3, 25, 30, 0.08) to rgba(3, 25, 30, 0.12) 

- Shadows: minimal; preferred elevation approximately 0 8px 30px rgba(3,25,30,0.06) 

## **3. Screen 01 — Session Setup** 

Purpose: Configure the conversation partner, voice style, and reference material before entering a call and another section for viewing previous sessions 

Reference flow: 1. Select partner → select voice → attach references → test microphone → Start Call 

2. Select a previous session 

### **Required sections** 

- Header / navigation: Aura / Voice Conversation branding and profile affordance. 

- Conversation partner area: "Our Experts " with four selectable personas: Neha, Alena, Sora , Aria. 

- Voice Style: 2 voice styles. 

- Reference Notes: upload/drop zone plus attached files and remove controls. 

- Bottom action area: Start Call. 

Page 2 

###### **AURA VOICE STUDIO  /  UI DESIGN PLAN** 

- Selected partner summary: partner name + voice + attachment count. 

### **Primary interaction** 

Start Call. It should be the strongest CTA on the page and use Ink Black as the default filled treatment. 

### **Interaction / visual rules** 

- Selected partner is visually obvious with a subtle Pearl Beige state and check indicator. 

- Persona cards must feel editorial/premium, not like generic admin forms. 

- File rows show filename, size and contextual information such as page count where available. 

- Primary CTA uses Ink Black with Ghost White text; hover/focus may introduce Pearl Beige as an accent. 

- Do not crowd the setup page with secondary controls. 

## **4. Screen 02 — Live Voice Call** 

Purpose: Provide an immersive, low-distraction voice conversation experience with clear system state. 

Reference flow: Connected → listening → thinking/speaking → pause/mute → End Call 

### **Required sections** 

- Top bar: Aura — Voice Session, connection state, copy/share actions. 

- Central voice presence: Aura identity, breathing aura, ripple/pulse states. 

- Current speech state: "Aura is speaking..." plus waveform/progress feedback. 

- Conversation area: turn-by-turn transcript with participant identity and timestamps. 

- Session Context panel: persona summary, referenced files/sections, spatial voice / audio state. 

- Bottom controls: microphone/mute, pause affordance, End Call. 

### **Primary interaction** 

End Call is the destructive action and must remain visually separated from microphone controls. 

### **Interaction / visual rules** 

- The central aura is the primary feedback mechanism and must remain visually dominant. 

- Idle: slow breathing. Listening: slight expansion. Speaking: waveform + breathing. Thinking: slower ripple. Muted/disconnected: reduced visual intensity. 

- Motion should feel organic and calm, not like a gaming HUD. 

- Keep the live screen from becoming a dashboard: voice presence → current speech → conversation → context. 

- Controls stay intentionally limited to reduce cognitive load. 

Page 3 

**AURA VOICE STUDIO  /  UI DESIGN PLAN** 

## **5. Screen 03 — Post-Call / Session Debrief** 

Purpose: Turn a completed call into replayable evidence, transcript context, and actionable conclusions. 

Reference flow: Open session → replay → inspect sentiment → read transcript → review overview → takeaways → metrics → export 

### **Required sections** 

- Session header with New Session / session title / date and duration. 

- Playback module with current time, full duration, playhead, sync state and turn count. 

- Sentiment & Engagement Flow with timeline markers such as Intro, Latency Clarification, Buffer Inquiry, Active Playhead. 

- Conversation Transcript with search, speaker labels, timestamps, highlighted playing turn. 

- Meeting Overview: purpose, participants, duration, dialogue flow, date. 

- Key Takeaways & Agreed Decisions: concise decision-oriented summary. 

- Call Metrics: duration, dialogue turns, average latency, P95 latency / stream status. 

- Export menu: TXT Transcript, PDF Summary, MP3 Full Audio, Copy JSON Content. 

### **Primary interaction** 

Export is the primary utility action. The individual export types should live inside one compact Export menu rather than four persistent toolbar buttons. 

### **Interaction / visual rules** 

- Use three information layers: Replay (what happened), Transcript (what was said), Intelligence (what it means). 

- Playing transcript row should be clearly distinguished without overwhelming neighboring turns. 

- Timeline labels must be legible at a glance and align precisely with the playback position. 

- Summary language should be concise and decision-oriented. 

- Metrics should remain visually subordinate to the narrative while still being easy to scan. 

## **6. Screen 04 — Analytics & Performance** 

Purpose: Provide a system-level view of conversation quality, technical performance, sentiment, and persona telemetry. 

Reference flow: Overview → daily volume → sentiment/topics → latency/jitter → persona performance 

### **Required sections** 

- Header: New Session navigation plus Analytics & Performance title. 

- KPI strip: Total Sessions, Completion, Avg Duration, Efficiency, Avg Sentiment Score, Roundtrip Latency. 

Page 4 

###### **AURA VOICE STUDIO  /  UI DESIGN PLAN** 

- Daily Conversation Volume: direct voice sessions vs relay fallbacks. 

- Sentiment Breakdown: 30-day index with Positive, Neutral/Inquisitive, and Friction/Escalation. 

- Topics: categorized call distribution such as Arch & Edge, Billing, Handshake, API, Integration, Codecs, Retrieval. 

- Turn Latency & Stream Jitter: edge handshake, relay buffer, fallback variance, SLA/target markers. 

- Agent & Persona Performance Registry: persona, model/deployment, region, session count, duration, sentiment alignment, P95 latency, handoff success. 

- Pagination / table navigation: Previous, Next. 

### **Primary interaction** 

The KPI strip is the primary scan target. The registry is the operational detail layer. 

### **Interaction / visual rules** 

- Use a strict four-level hierarchy: KPI strip → behavior charts → technical performance → operational table. 

- Charts should be restrained and information-dense without decorative gradients or excessive legends. 

- Technical thresholds such as target and SLA max should be visually clear but not alarmist. 

- The persona table must support scanning of model/version and region metadata without breaking column alignment. 

- Dense data does not justify smaller typography below legibility thresholds; preserve breathing room. 

## **7. Shared Component Architecture** 

All four screens should be built from a common component library. This is essential for pixel consistency and reduces visual drift during implementation. 

|**Category**|**Components**|
|---|---|
|Navigation|AppHeader, BackNavigation, PageTitle, SessionStatus|
|Cards|MetricCard, PersonaCard, VoiceCard, ContextCard,<br>SummaryCard|
|Voice|AuraVisualizer, VoiceWaveform, CallControls,<br>ConnectionIndicator|
|Conversation|Transcript, TranscriptMessage, TranscriptTimestamp,<br>SpeakingIndicator|
|Data|LineChart, SentimentChart, TopicChart, LatencyChart,<br>PerformanceTable|
|Files|FileDropzone, FileAttachment, ExportMenu|



Page 5 

**AURA VOICE STUDIO  /  UI DESIGN PLAN** 

## **8. Responsive & Accessibility Baseline** 

- Desktop-first reference: optimize the supplied composition around 1440 px width while preserving a usable 1280 px layout. 

- Tablet: collapse multi-column modules to stacked sections while keeping primary actions persistent. 

- Mobile: prioritize one focused content column; live call keeps the central aura, speech state, and essential controls visible at all times. 

- Touch targets: controls should use comfortable hit areas and clear focus states. 

- Contrast: Ink Black on Ghost White should carry primary text and controls; Pearl Beige is an accent, not body text. 

- Motion accessibility: provide reduced-motion behavior for aura and chart animations when requested by the operating system. 

## **9. Pixel-Perfection Implementation Rules** 

- Build tokens first: typography, colors, spacing, radii, borders, icon sizing, button states, then screen-specific layouts. 

- Never tune four pages independently. Shared components must remain the source of truth. 

- Lock horizontal rhythm and vertical spacing before polishing decorative motion. 

- Use exact iconography already established in the supplied screens where possible (Material Symbols Outlined and existing icon semantics). 

- Avoid one-off pixel values unless they are necessary to match the reference. Prefer the shared spacing scale. 

- Use consistent baseline alignment for headings, icon/text pairs, table cells, chart labels, and control groups. 

- Hover, focus, selected, disabled, speaking, muted, loading, and disconnected states must be defined for every interactive component. 

- Visual QA must compare the rendered page against the reference at the target viewport and inspect typography, spacing, alignment, border weight, radius, icon position, and responsive behavior. 

## **10. End-to-End UX Journey** 

|**01 Prepare**|**02 Talk**|**03 Understand**|**04 Improve**|
|---|---|---|---|
|Partner + voice|Live aura + transcript|Replay + summary|KPIs + telemetry|
|References|Current speech|Decisions|Performance|
|Microphone test|Call controls|Export|New session|



Page 6 

**AURA VOICE STUDIO  /  UI DESIGN PLAN** 

## **11. Reference Files Used** 

This plan was prepared from the four supplied design files and their existing UI/content structure: session page, voice call page, post-call page, and Analytics page. The plan preserves their established naming, interaction concepts, and content hierarchy while formalizing the shared design system for implementation. 

#### **Design principle: Calm, precise, intelligent, responsive.** 

## **12. Pixel-Perfection Testing & QA Checklist** 

Verification steps to run in Figma before implementation and again against the rendered build. Organized by the same categories as the design system above. 

### **12.1 Spacing & Grid** 

- Snap all paddings, item spacing, and counter-axis spacing to the shared spacing scale (4/8/12/16/20/24/32/40/48/64/80 px) — no fractional or off-scale values. 

- Audit gutters between cards, panels, and columns; confirm all instances of a given pattern use the same value (do not let sibling columns/lists drift, e.g. 20px vs 24px). 

- Verify padding is symmetric inside buttons, cards, and badges (top/bottom, left/right) unless asymmetry is a deliberate, documented exception. 

- Overlay the 12-column grid in Figma and confirm every module aligns to it rather than "close enough" placement. 

### **12.2 Typography** 

- Confirm Montserrat (and JetBrains Mono for technical/export content) is applied consistently, with no fallback-font leakage. 

- Lock a line-height ratio per text role: ~1.1–1.3 for Display/Page title/Section title, ~1.4–1.6 for Body, tighter for Metadata. 

- Check letter-spacing on headings and metrics — no default Figma auto-tracking left unreviewed. 

- Confirm text styles (Display, Page title, Section title, Body, Metadata, Metrics) are saved as reusable Figma text styles, not ad-hoc per-instance sizing. 

### **12.3 Color** 

- Set Ink Black, Pearl Beige, Ghost White, and any status colors as Figma color styles/variables; no raw hex on individual layers. 

- Check contrast ratios meet WCAG AA for body text: Ink Black on Ghost White, and any text on Pearl Beige. 

- Scan for stray off-palette grays or shadow colors introduced by AI generation that don’t map to a defined token. 

Page 7 

**AURA VOICE STUDIO  /  UI DESIGN PLAN** 

### **12.4 Components & Consistency** 

- Convert repeated elements (PersonaCard, VoiceCard, MetricCard, AuraVisualizer, TranscriptMessage, etc.) into Figma components with explicit variants for every required state. 

- Confirm corner radius per component type is consistent and pulled only from the radius scale (8/12/16/24/pill). 

- Check icon sizing and stroke weight match across a screen (Material Symbols Outlined at one consistent weight). 

- Confirm border widths are consistent within a component family; opacity should vary only within the defined rgba(3,25,30,0.08–0.12) range, not width. 

### **12.5 Layout Precision** 

- Use Figma’s alignment tools (not eyeballing) to confirm true center/left alignment across headings, icon/text pairs, and control groups. 

- Verify the AuraVisualizer and its waveform/ripple ring are perfectly concentric at every state. 

- Confirm the 12-column layout and any multi-panel screens (e.g. Live Call, Analytics) use defined fixed/fluid widths rather than ad-hoc sizing. 

### **12.6 States & Responsiveness** 

- Confirm all required aura/mic states (idle, listening, speaking, thinking, muted/disconnected) are designed explicitly, not implied. 

- Confirm hover, focus, selected, disabled, speaking, muted, loading, and disconnected states exist for every interactive component, per section 9. 

- Validate the tablet and mobile breakpoints defined in section 8 against real content (no overflow, no broken persistent actions). 

### **12.7 Shadows & Elevation** 

- Define distinct shadow tokens per elevation level (e.g. card, modal/overlay, dropdown) rather than one shared minimal shadow value. 

- Confirm no component uses a bespoke, undocumented box-shadow outside the defined tokens. 

Page 8 

