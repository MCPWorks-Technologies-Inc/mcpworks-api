# MCPWorks Design System

Style guide for MCPWorks surfaces. Source of truth: `www.mcpworks.io` (Tailwind CSS v4).

## Typography

| Role | Font | Tailwind Class | Weight Range |
|------|------|----------------|--------------|
| Headings | Space Grotesk | `font-display` | 300-700 |
| Body | DM Sans | `font-body` | 100-1000 |
| Code | System monospace | `font-mono` | -- |

Google Fonts URL:
```
https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,100..1000;1,9..40,100..1000&family=Space+Grotesk:wght@300..700&display=swap
```

Tailwind v4 theme definition:
```css
@theme {
  --font-display: "Space Grotesk", ui-sans-serif, system-ui, sans-serif;
  --font-body: "DM Sans", ui-sans-serif, system-ui, sans-serif;
}
```

### Type Scale

| Element | Classes |
|---------|---------|
| Hero headline | `text-4xl md:text-5xl font-bold leading-tight font-display` |
| Section heading | `text-2xl font-bold font-display` |
| CTA heading | `text-3xl font-bold font-display` |
| Body large | `text-xl text-gray-400` |
| Body | `text-base text-gray-300` (prose) or `text-gray-400` |
| Body small | `text-sm text-gray-400` |
| Caption / meta | `text-sm text-gray-500` |
| Subtle / muted | `text-sm text-gray-600` |
| Inline code | `bg-gray-800 px-2 py-1 rounded text-blue-400` |

## Colors

### Backgrounds

| Token | Hex (Tailwind default) | Usage |
|-------|------------------------|-------|
| `bg-gray-950` | `#030712` | Alternating sections, footer, terminal body, code blocks |
| `bg-gray-900` | `#111827` | Primary page background, alternating sections, header, terminal chrome |
| `bg-gray-800` | `#1f2937` | Cards, code blocks, inline code badges |

Sections alternate between `bg-gray-900` and `bg-gray-950` to break visual monotony without introducing new colors.

### Text

| Token | Usage |
|-------|-------|
| `text-white` | Primary headings, emphasized content |
| `text-gray-300` | Prose body, secondary headings, hover state for links |
| `text-gray-400` | Body text, descriptions, feature card copy |
| `text-gray-500` | Captions, meta text, code comments, nav links |
| `text-gray-600` | Muted text (e.g. "Free tier included"), copyright |

### Brand & Accent

| Token | Usage |
|-------|-------|
| `text-blue-500` | Brand name, accent keywords in headings, step numbers |
| `text-blue-400` | Links, inline code values, URLs in code blocks |
| `bg-blue-600` | Primary CTA background, "Popular" badge |
| `bg-blue-700` | Primary CTA hover |
| `text-green-400` | Success indicators, MCPWorks-positive comparisons |
| `text-red-400` | Warning/negative comparisons |
| `text-yellow-300` | Code string literals, function names in terminal output |

### Borders

| Token | Usage |
|-------|-------|
| `border-gray-800` | Section dividers, header/footer borders |
| `border-gray-700` | Card borders, code block borders, terminal chrome |
| `border-gray-600` | Secondary CTA border, hover state for cards |
| `border-blue-600` | Highlighted card (e.g. "Popular" pricing tier) |
| `border-red-900/50` | Negative comparison card tint |
| `border-green-900/50` | Positive comparison card tint |

## Spacing & Layout

| Pattern | Classes |
|---------|---------|
| Page max-width | `max-w-6xl` (hero, works-with), `max-w-5xl` (code-mode), `max-w-4xl` (content sections) |
| Container | `container mx-auto px-4` |
| Section padding | `py-16` (standard), `py-20 md:py-28` (hero), `py-10` (social proof bar) |
| Card padding | `p-6` (feature cards), `p-5` (pricing cards, comparison cards) |
| Section gap | No border dividers; alternating `bg-gray-900`/`bg-gray-950` |
| Grid gaps | `gap-12` (hero two-col), `gap-8` (three-col, comparisons), `gap-6` (two-col features), `gap-4` (four-col pricing) |

## Components

### Primary CTA Button
```html
<a class="bg-blue-600 hover:bg-blue-700 text-white font-medium px-8 py-3 rounded text-lg transition-colors">
    Get Started — Developer Preview
</a>
```

### Secondary CTA Button (Outline)
```html
<a class="border border-gray-600 hover:border-gray-400 text-gray-300 hover:text-white font-medium px-8 py-3 rounded text-lg transition-colors">
    Book a Demo
</a>
```

### Header Nav CTA (Small)
```html
<a class="bg-blue-600 hover:bg-blue-700 text-white text-sm font-medium px-4 py-2 rounded transition-colors">
    Get Started
</a>
```

### Nav Link
```html
<a class="text-gray-400 hover:text-white text-sm">Link</a>
```

### Feature Card
```html
<div class="bg-gray-800 rounded-lg p-6 border border-gray-700
            transition-all duration-200 hover:-translate-y-0.5
            hover:border-gray-600 hover:shadow-lg hover:shadow-blue-500/10">
    <h4 class="font-semibold text-lg mb-2">Title</h4>
    <p class="text-gray-400 text-sm">Description</p>
</div>
```

### Pricing Card
```html
<div class="bg-gray-800 rounded-lg p-5 border border-gray-700 text-center
            transition-all duration-200 hover:-translate-y-1
            hover:shadow-xl hover:shadow-black/30">
    <h4 class="font-semibold mb-1">Tier Name</h4>
    <div class="text-2xl font-bold mb-3">$X<span class="text-sm text-gray-500">/mo</span></div>
    <ul class="text-gray-400 text-sm space-y-1 text-left">
        <li>Feature</li>
    </ul>
</div>
```

### Highlighted Pricing Card (Popular)
Same as pricing card but with:
- `border-blue-600` instead of `border-gray-700`
- Badge: `<span class="absolute -top-3 left-1/2 -translate-x-1/2 bg-blue-600 text-white text-xs font-medium px-3 py-1 rounded-full">Popular</span>`

### Terminal Mockup
```html
<div class="bg-gray-950 rounded-lg border border-gray-700 overflow-hidden shadow-2xl">
    <!-- Chrome bar -->
    <div class="flex items-center gap-2 px-4 py-3 bg-gray-900 border-b border-gray-700">
        <div class="w-3 h-3 rounded-full bg-red-500/80"></div>
        <div class="w-3 h-3 rounded-full bg-yellow-500/80"></div>
        <div class="w-3 h-3 rounded-full bg-green-500/80"></div>
        <span class="text-gray-500 text-xs ml-2 font-mono">terminal-title</span>
    </div>
    <!-- Content -->
    <pre class="p-5 text-sm font-mono overflow-x-auto leading-relaxed"><code>...</code></pre>
</div>
```

### Code Block (Inline in page)
```html
<div class="bg-gray-800 rounded-lg border border-gray-700 p-6">
    <pre class="text-sm overflow-x-auto"><code class="text-gray-300">...</code></pre>
</div>
```

### Footer Column
```html
<div>
    <h5 class="text-sm font-semibold text-gray-300 mb-3">Column Title</h5>
    <ul class="space-y-2 text-sm">
        <li><a href="#" class="text-gray-500 hover:text-gray-300">Link</a></li>
    </ul>
</div>
```

## Code Syntax Highlighting

Manual span-based highlighting in code blocks:

| Token Type | Class |
|------------|-------|
| Keys / property names | `text-blue-400` |
| String values | `text-yellow-300` |
| Object names / labels | `text-green-400` |
| Comments / secondary | `text-gray-500` |
| Default text | `text-gray-300` or `text-gray-400` |
| Success checkmarks | `text-green-400` |
| Negative values | `text-red-400` |

## Animation

### Page-load fade-in
```css
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(10px); }
  to { opacity: 1; transform: translateY(0); }
}

.fade-in        { animation: fadeIn 0.4s ease-out; }
.fade-in-delay  { animation: fadeIn 0.4s ease-out 0.15s both; }
.fade-in-delay-2 { animation: fadeIn 0.4s ease-out 0.3s both; }
```

### Scroll-triggered (progressive enhancement)
```css
@supports (animation-timeline: view()) {
  .scroll-fade-in {
    opacity: 0;
    transform: translateY(20px);
    animation: fadeIn 0.6s ease-out both;
    animation-timeline: view();
    animation-range: entry 0% entry 30%;
  }
}
```

### Interactive transitions
- Feature cards: `transition-all duration-200 hover:-translate-y-0.5`
- Pricing cards: `transition-all duration-200 hover:-translate-y-1`
- Buttons/links: `transition-colors`

## Prose (Blog / Long-form)

Uses `@tailwindcss/typography` with these overrides:

```
prose prose-invert prose-blue max-w-none
prose-headings:font-bold
prose-h2:text-2xl prose-h2:mt-10 prose-h2:mb-4
prose-h3:text-xl prose-h3:mt-8 prose-h3:mb-3
prose-p:text-gray-300 prose-p:leading-relaxed
prose-a:text-blue-400 prose-a:no-underline hover:prose-a:underline
prose-code:bg-gray-800 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-blue-300
prose-pre:bg-gray-800 prose-pre:border prose-pre:border-gray-700
prose-li:text-gray-300
prose-strong:text-white
```

## Brand

| Element | Value |
|---------|-------|
| Name | MCPWorks |
| Tagline | Code Sandbox for AI Assistants |
| Brand color | `text-blue-500` / `bg-blue-600` |
| Brand font | Space Grotesk, bold |
| Legal entity | MCPWorks Technologies Inc. |
| Contact | hello@mcpworks.io |
| Social | Bluesky (@mcpworks.io) |
