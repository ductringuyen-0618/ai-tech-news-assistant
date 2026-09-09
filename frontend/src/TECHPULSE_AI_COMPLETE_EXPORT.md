# TechPulse AI - Complete Project Export

**Version:** 1.0.0  
**Generated:** October 17, 2025  
**Theme:** Futuristic Light  
**Framework:** React + TypeScript + Tailwind CSS 4.0  
**Backend:** Supabase Edge Functions (Hono)

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Architecture](#architecture)
3. [Setup Instructions](#setup-instructions)
4. [File Structure](#file-structure)
5. [Complete Source Code](#complete-source-code)
6. [Environment Configuration](#environment-configuration)
7. [Package Dependencies](#package-dependencies)
8. [Features](#features)

---

## Project Overview

**TechPulse AI** is an AI-powered tech news aggregation platform that:

- Pulls news from multiple sources with de-duplication
- Uses AI to summarize articles at different detail levels
- Provides smart topic categorization and personalized feeds
- Features conversational Q&A search
- Generates daily/weekly digests
- Includes semantic search capabilities
- Offers Agentic Research Mode with Markdown export
- Shows Source Transparency with credibility scores
- Visualizes Knowledge Graph of tech ecosystem relationships

### Key Features

1. **News Feed** - Browse categorized tech news with multiple view modes
2. **Research Mode** - AI agent conducts comprehensive research on queries
3. **Knowledge Graph** - Interactive visualization of tech ecosystem
   relationships
4. **Daily Digest** - Curated summary of top stories
5. **Ask AI** - Conversational search interface
6. **Settings** - Topic preferences with visual feedback

---

## Architecture

### Frontend

- **React 18** with TypeScript
- **Tailwind CSS 4.0** for styling
- **shadcn/ui** component library
- **Lucide React** for icons
- **Sonner** for toast notifications

### Backend

- **Supabase** for database and authentication
- **Edge Functions** (Deno runtime)
- **Hono** web framework
- **Key-Value Store** for user preferences

### Design System

- **Font:** Space Grotesk (headings), Inter (body)
- **Colors:** White Smoke (#F9FAFB), Rich Black-Gray (#111827)
- **Primary:** Blue gradient (#3B82F6 → #2563EB)
- **Accent:** Purple gradient (#8B5CF6 → #6366F1)

---

## Setup Instructions

### Prerequisites

- Node.js 18+ or Bun
- Supabase account (free tier works)

### Local Development Setup

#### 1. Create Project Directory

```bash
mkdir techpulse-ai
cd techpulse-ai
```

#### 2. Create `package.json`

```json
{
  "name": "techpulse-ai",
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "lucide-react": "latest",
    "sonner": "^2.0.3",
    "@radix-ui/react-slot": "^1.1.2",
    "@radix-ui/react-dialog": "latest",
    "@radix-ui/react-popover": "latest",
    "@radix-ui/react-checkbox": "latest",
    "@radix-ui/react-label": "latest",
    "@radix-ui/react-separator": "latest",
    "@radix-ui/react-tabs": "latest",
    "@radix-ui/react-scroll-area": "latest",
    "@radix-ui/react-select": "latest",
    "@radix-ui/react-switch": "latest",
    "@radix-ui/react-textarea": "latest",
    "@radix-ui/react-hover-card": "latest",
    "class-variance-authority": "^0.7.1",
    "clsx": "latest",
    "tailwind-merge": "latest"
  },
  "devDependencies": {
    "@types/react": "^18.3.1",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "vite": "^5.2.0",
    "typescript": "^5.4.5",
    "tailwindcss": "^4.0.0",
    "autoprefixer": "^10.4.19",
    "postcss": "^8.4.38"
  }
}
```

#### 3. Create `vite.config.ts`

```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './'),
    },
  },
});
```

#### 4. Create `tsconfig.json`

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["ES2020", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "paths": {
      "@/*": ["./*"]
    }
  },
  "include": ["**/*.ts", "**/*.tsx"],
  "exclude": ["node_modules"]
}
```

#### 5. Create `index.html`

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>TechPulse AI - AI-Powered Tech News Aggregation</title>
    <meta
      name="description"
      content="Stay ahead with AI-curated tech news from TechCrunch, The Verge, Wired, and more."
    />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/main.tsx"></script>
  </body>
</html>
```

#### 6. Create `main.tsx`

```typescript
import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './styles/globals.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
```

#### 7. Install Dependencies

```bash
npm install
```

#### 8. Set Up Supabase

1. Create a project at https://supabase.com
2. Get your Project URL and API keys from Settings → API
3. Update `/utils/supabase/info.tsx` with your credentials
4. Deploy the edge function:

```bash
# Install Supabase CLI
npm install -g supabase

# Login to Supabase
supabase login

# Link your project
supabase link --project-ref YOUR_PROJECT_REF

# Deploy the edge function
supabase functions deploy make-server-3889d4d6
```

#### 9. Run Development Server

```bash
npm run dev
```

Your app should now be running at `http://localhost:5173`

---

## File Structure

```
techpulse-ai/
├── index.html
├── main.tsx
├── package.json
├── tsconfig.json
├── vite.config.ts
├── App.tsx
├── Attributions.md
├── components/
│   ├── ChatInterface.tsx
│   ├── DigestView.tsx
│   ├── KnowledgeGraph.tsx
│   ├── NewsCard.tsx
│   ├── ResearchMode.tsx
│   ├── SearchBar.tsx
│   ├── TopicFilter.tsx
│   ├── figma/
│   │   └── ImageWithFallback.tsx
│   └── ui/
│       ├── accordion.tsx
│       ├── alert-dialog.tsx
│       ├── alert.tsx
│       ├── aspect-ratio.tsx
│       ├── avatar.tsx
│       ├── badge.tsx
│       ├── breadcrumb.tsx
│       ├── button.tsx
│       ├── calendar.tsx
│       ├── card.tsx
│       ├── carousel.tsx
│       ├── chart.tsx
│       ├── checkbox.tsx
│       ├── collapsible.tsx
│       ├── command.tsx
│       ├── context-menu.tsx
│       ├── dialog.tsx
│       ├── drawer.tsx
│       ├── dropdown-menu.tsx
│       ├── form.tsx
│       ├── hover-card.tsx
│       ├── input-otp.tsx
│       ├── input.tsx
│       ├── label.tsx
│       ├── menubar.tsx
│       ├── navigation-menu.tsx
│       ├── pagination.tsx
│       ├── popover.tsx
│       ├── progress.tsx
│       ├── radio-group.tsx
│       ├── resizable.tsx
│       ├── scroll-area.tsx
│       ├── select.tsx
│       ├── separator.tsx
│       ├── sheet.tsx
│       ├── sidebar.tsx
│       ├── skeleton.tsx
│       ├── slider.tsx
│       ├── sonner.tsx
│       ├── switch.tsx
│       ├── table.tsx
│       ├── tabs.tsx
│       ├── textarea.tsx
│       ├── toggle-group.tsx
│       ├── toggle.tsx
│       ├── tooltip.tsx
│       ├── use-mobile.ts
│       └── utils.ts
├── styles/
│   └── globals.css
├── supabase/
│   └── functions/
│       └── server/
│           ├── index.tsx
│           └── kv_store.tsx (protected - auto-generated)
└── utils/
    └── supabase/
        └── info.tsx
```

---

## Complete Source Code

### Core Application Files

#### `/App.tsx`

```typescript
import { useState, useEffect } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./components/ui/tabs";
import { Button } from "./components/ui/button";
import { Badge } from "./components/ui/badge";
import { Toaster } from "./components/ui/sonner";
import { toast } from "sonner@2.0.3";
import { NewsCard } from "./components/NewsCard";
import { TopicFilter } from "./components/TopicFilter";
import { SearchBar } from "./components/SearchBar";
import { DigestView } from "./components/DigestView";
import { ChatInterface } from "./components/ChatInterface";
import { ResearchMode } from "./components/ResearchMode";
import { KnowledgeGraph } from "./components/KnowledgeGraph";
import { Newspaper, Settings, Mail, MessageCircle, TrendingUp, Loader2, Grid, List, Lightbulb, Network } from "lucide-react";
import { projectId, publicAnonKey } from "./utils/supabase/info";

export default function App() {
  const [articles, setArticles] = useState<any[]>([]);
  const [filteredArticles, setFilteredArticles] = useState<any[]>([]);
  const [selectedCategories, setSelectedCategories] = useState<string[]>(["AI/ML", "AI Agents"]);
  const [searchQuery, setSearchQuery] = useState("");
  const [digest, setDigest] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [viewMode, setViewMode] = useState<"compact" | "detailed">("detailed");
  const [showTrendingOnly, setShowTrendingOnly] = useState(false);
  const [isSavingPreferences, setIsSavingPreferences] = useState(false);
  const [savedCategories, setSavedCategories] = useState<string[]>([]);
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);

  const baseUrl = `https://${projectId}.supabase.co/functions/v1/make-server-3889d4d6`;

  // Fetch articles
  const fetchArticles = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (selectedCategories.length > 0) {
        params.append("categories", selectedCategories.join(","));
      }
      if (searchQuery) {
        params.append("search", searchQuery);
      }
      if (showTrendingOnly) {
        params.append("trending", "true");
      }

      const response = await fetch(`${baseUrl}/news?${params}`, {
        headers: {
          Authorization: `Bearer ${publicAnonKey}`,
        },
      });

      if (!response.ok) throw new Error("Failed to fetch news");

      const data = await response.json();
      setArticles(data.articles);
      setFilteredArticles(data.articles);
    } catch (error) {
      console.error("Error fetching articles:", error);
    } finally {
      setLoading(false);
    }
  };

  // Fetch digest
  const fetchDigest = async () => {
    try {
      const response = await fetch(`${baseUrl}/digest?userId=default`, {
        headers: {
          Authorization: `Bearer ${publicAnonKey}`,
        },
      });

      if (!response.ok) throw new Error("Failed to fetch digest");

      const data = await response.json();
      setDigest(data);
    } catch (error) {
      console.error("Error fetching digest:", error);
    }
  };

  // Save preferences
  const savePreferences = async () => {
    setIsSavingPreferences(true);
    try {
      const response = await fetch(`${baseUrl}/preferences?userId=default`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${publicAnonKey}`,
        },
        body: JSON.stringify({
          categories: selectedCategories,
          digestFrequency: "daily",
        }),
      });

      if (!response.ok) throw new Error("Failed to save preferences");

      // Update saved categories state
      setSavedCategories([...selectedCategories]);
      setHasUnsavedChanges(false);

      toast.success("Preferences saved successfully!", {
        description: `Your feed will now show ${selectedCategories.length} selected topic${selectedCategories.length !== 1 ? 's' : ''}.`,
        duration: 3000,
      });

      // Refresh articles after saving preferences
      await fetchArticles();
    } catch (error) {
      console.error("Error saving preferences:", error);
      toast.error("Failed to save preferences", {
        description: "Please try again later.",
        duration: 3000,
      });
    } finally {
      setIsSavingPreferences(false);
    }
  };

  // Ask question in chat
  const handleAskQuestion = async (question: string) => {
    try {
      const response = await fetch(`${baseUrl}/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${publicAnonKey}`,
        },
        body: JSON.stringify({ question }),
      });

      if (!response.ok) throw new Error("Failed to process question");

      return await response.json();
    } catch (error) {
      console.error("Error processing question:", error);
      throw error;
    }
  };

  // Load preferences and articles on mount
  useEffect(() => {
    const loadData = async () => {
      try {
        const response = await fetch(`${baseUrl}/preferences?userId=default`, {
          headers: {
            Authorization: `Bearer ${publicAnonKey}`,
          },
        });

        if (response.ok) {
          const prefs = await response.json();
          const cats = prefs.categories || ["AI/ML", "AI Agents"];
          setSelectedCategories(cats);
          setSavedCategories(cats);
        }
      } catch (error) {
        console.error("Error loading preferences:", error);
      }

      fetchArticles();
      fetchDigest();
    };

    loadData();
  }, []);

  // Check for unsaved changes
  useEffect(() => {
    const categoriesChanged = JSON.stringify(selectedCategories.sort()) !== JSON.stringify(savedCategories.sort());
    setHasUnsavedChanges(categoriesChanged);
  }, [selectedCategories, savedCategories]);

  // Refetch when filters change
  useEffect(() => {
    fetchArticles();
  }, [selectedCategories, searchQuery, showTrendingOnly]);

  return (
    <div className="min-h-screen bg-gradient-to-br from-gray-50 via-white to-gray-50 subtle-pattern">
      {/* Header */}
      <header className="bg-white/80 backdrop-blur-lg border-b border-gray-200 shadow-sm sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 gradient-primary rounded-xl flex items-center justify-center shadow-md">
                <Newspaper className="w-6 h-6 text-white" />
              </div>
              <div>
                <h1 className="text-2xl text-gradient">TechPulse AI</h1>
                <p className="text-sm text-gray-600">AI-Powered Tech News Aggregation</p>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant="outline" className="gap-1 border-orange-200 bg-orange-50 text-orange-700">
                <span>🔥</span>
                {articles.filter((a) => a.trending).length} Trending
              </Badge>
              <Badge variant="outline" className="gap-1 border-blue-200 bg-blue-50 text-blue-700">
                {articles.length} Articles Today
              </Badge>
            </div>
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-4 py-6">
        <Tabs defaultValue="feed" className="space-y-6">
          <TabsList className="grid grid-cols-6 w-full max-w-4xl mx-auto">
            <TabsTrigger value="feed" className="gap-2">
              <Newspaper className="w-4 h-4" />
              News Feed
            </TabsTrigger>
            <TabsTrigger value="research" className="gap-2">
              <Lightbulb className="w-4 h-4" />
              Research
            </TabsTrigger>
            <TabsTrigger value="knowledge" className="gap-2">
              <Network className="w-4 h-4" />
              Knowledge
            </TabsTrigger>
            <TabsTrigger value="digest" className="gap-2">
              <Mail className="w-4 h-4" />
              Digest
            </TabsTrigger>
            <TabsTrigger value="chat" className="gap-2">
              <MessageCircle className="w-4 h-4" />
              Ask AI
            </TabsTrigger>
            <TabsTrigger value="preferences" className="gap-2 relative">
              <Settings className="w-4 h-4" />
              Settings
              {hasUnsavedChanges && (
                <span className="absolute -top-1 -right-1 w-2 h-2 bg-yellow-500 rounded-full animate-pulse" />
              )}
            </TabsTrigger>
          </TabsList>

          {/* News Feed Tab */}
          <TabsContent value="feed" className="space-y-6">
            <div className="flex flex-col md:flex-row gap-4 items-start md:items-center justify-between">
              <div className="flex-1 w-full md:max-w-md">
                <SearchBar onSearch={setSearchQuery} />
              </div>
              <div className="flex gap-2 items-center">
                <Button
                  variant={showTrendingOnly ? "default" : "outline"}
                  size="sm"
                  onClick={() => setShowTrendingOnly(!showTrendingOnly)}
                  className="gap-2"
                >
                  <TrendingUp className="w-4 h-4" />
                  Trending Only
                </Button>
                <div className="flex gap-1 border rounded-lg p-1">
                  <Button
                    variant={viewMode === "detailed" ? "default" : "ghost"}
                    size="sm"
                    onClick={() => setViewMode("detailed")}
                  >
                    <Grid className="w-4 h-4" />
                  </Button>
                  <Button
                    variant={viewMode === "compact" ? "default" : "ghost"}
                    size="sm"
                    onClick={() => setViewMode("compact")}
                  >
                    <List className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            </div>

            {selectedCategories.length > 0 && (
              <div className="flex flex-wrap gap-2 items-center bg-white p-4 rounded-xl border border-gray-200 elevation-sm">
                <span className="text-sm text-gray-600">Filtered by:</span>
                {selectedCategories.map((cat) => (
                  <Badge key={cat} variant="secondary" className="bg-blue-50 text-blue-700 border-blue-200">
                    {cat}
                  </Badge>
                ))}
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setSelectedCategories([])}
                  className="ml-auto text-gray-600 hover:text-blue-600"
                >
                  Clear Filters
                </Button>
              </div>
            )}

            {loading ? (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
              </div>
            ) : filteredArticles.length === 0 ? (
              <div className="text-center py-12 bg-white rounded-xl border border-gray-200 elevation-md">
                <Newspaper className="w-12 h-12 text-blue-600 mx-auto mb-3" />
                <h3 className="text-lg mb-2 text-gray-900">No articles found</h3>
                <p className="text-gray-600 mb-4">
                  Try adjusting your filters or search query
                </p>
                <Button onClick={() => {
                  setSearchQuery("");
                  setShowTrendingOnly(false);
                  setSelectedCategories([]);
                }} className="gradient-primary text-white">
                  Reset Filters
                </Button>
              </div>
            ) : (
              <div className={`grid gap-6 ${
                viewMode === "detailed"
                  ? "grid-cols-1 lg:grid-cols-2"
                  : "grid-cols-1"
              }`}>
                {filteredArticles.map((article) => (
                  <NewsCard
                    key={article.id}
                    article={article}
                    viewMode={viewMode}
                  />
                ))}
              </div>
            )}
          </TabsContent>

          {/* Research Mode Tab */}
          <TabsContent value="research">
            <ResearchMode baseUrl={baseUrl} publicAnonKey={publicAnonKey} />
          </TabsContent>

          {/* Knowledge Graph Tab */}
          <TabsContent value="knowledge">
            <KnowledgeGraph baseUrl={baseUrl} publicAnonKey={publicAnonKey} />
          </TabsContent>

          {/* Daily Digest Tab */}
          <TabsContent value="digest">
            {digest ? (
              <DigestView digest={digest} />
            ) : (
              <div className="flex items-center justify-center py-12">
                <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
              </div>
            )}
          </TabsContent>

          {/* Chat Tab */}
          <TabsContent value="chat">
            <div className="max-w-4xl mx-auto">
              <ChatInterface onAskQuestion={handleAskQuestion} />
            </div>
          </TabsContent>

          {/* Preferences Tab */}
          <TabsContent value="preferences">
            <div className="max-w-4xl mx-auto">
              <TopicFilter
                selectedCategories={selectedCategories}
                onCategoriesChange={setSelectedCategories}
                onSave={savePreferences}
                isSaving={isSavingPreferences}
                hasUnsavedChanges={hasUnsavedChanges}
              />
            </div>
          </TabsContent>
        </Tabs>
      </div>

      {/* Toast Notifications */}
      <Toaster position="bottom-right" />

      {/* Footer */}
      <footer className="bg-white border-t border-gray-200 mt-12">
        <div className="max-w-7xl mx-auto px-4 py-6">
          <div className="flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 gradient-primary rounded-lg flex items-center justify-center shadow-md">
                <Newspaper className="w-4 h-4 text-white" />
              </div>
              <span className="text-sm text-gray-700">
                TechPulse AI - Your personalized tech news hub
              </span>
            </div>
            <p className="text-sm text-gray-500">
              Aggregating from TechCrunch, The Verge, Wired, Ars Technica & more
            </p>
          </div>
        </div>
      </footer>
    </div>
  );
}
```

### Component Files

#### `/components/NewsCard.tsx`

```typescript
import { useState } from "react";
import { ImageWithFallback } from "./figma/ImageWithFallback";
import { ExternalLink, TrendingUp, Clock, ChevronDown, ChevronUp, Shield, Info } from "lucide-react";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "./ui/card";
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "./ui/hover-card";

interface NewsCardProps {
  article: {
    id: string;
    title: string;
    source: string;
    url: string;
    publishedAt: string;
    imageUrl: string;
    category: string[];
    summaryShort: string;
    summaryMedium: string;
    keyInsights: string[];
    sentiment: string;
    trending: boolean;
    credibilityScore?: number;
    sourcesUsed?: string[];
  };
  viewMode: "compact" | "detailed";
}

export function NewsCard({ article, viewMode }: NewsCardProps) {
  const [expanded, setExpanded] = useState(false);

  const timeAgo = (dateString: string) => {
    const date = new Date(dateString);
    const now = new Date();
    const hours = Math.floor((now.getTime() - date.getTime()) / (1000 * 60 * 60));

    if (hours < 1) return "Just now";
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    return `${days}d ago`;
  };

  const sentimentColor = {
    positive: "text-green-600",
    negative: "text-red-600",
    mixed: "text-yellow-600"
  }[article.sentiment] || "text-gray-600";

  const getCredibilityColor = (score: number) => {
    if (score >= 90) return "text-green-600";
    if (score >= 70) return "text-blue-600";
    if (score >= 50) return "text-yellow-600";
    return "text-red-600";
  };

  const getCredibilityLabel = (score: number) => {
    if (score >= 90) return "Highly Reliable";
    if (score >= 70) return "Reliable";
    if (score >= 50) return "Moderate";
    return "Limited";
  };

  if (viewMode === "compact") {
    return (
      <Card className="hover:shadow-lg transition-shadow">
        <CardHeader className="pb-3">
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-2 flex-wrap">
                {article.trending && (
                  <Badge variant="default" className="bg-orange-500">
                    <TrendingUp className="w-3 h-3 mr-1" />
                    Trending
                  </Badge>
                )}
                <span className="text-sm text-gray-500">{article.source}</span>
                {article.credibilityScore !== undefined && (
                  <>
                    <span className="text-sm text-gray-400">•</span>
                    <HoverCard>
                      <HoverCardTrigger asChild>
                        <span className={`text-sm flex items-center gap-1 cursor-help ${getCredibilityColor(article.credibilityScore)}`}>
                          <Shield className="w-3 h-3" />
                          {article.credibilityScore}%
                        </span>
                      </HoverCardTrigger>
                      <HoverCardContent className="w-80">
                        <div className="space-y-2">
                          <h4 className="font-semibold flex items-center gap-2">
                            <Shield className="w-4 h-4" />
                            Source Credibility
                          </h4>
                          <div className="space-y-1">
                            <div className="flex items-center justify-between">
                              <span className="text-sm text-gray-600">Reliability:</span>
                              <span className={`text-sm font-semibold ${getCredibilityColor(article.credibilityScore)}`}>
                                {getCredibilityLabel(article.credibilityScore)}
                              </span>
                            </div>
                            <div className="w-full bg-gray-200 h-2 rounded-full overflow-hidden">
                              <div
                                className={`h-full ${article.credibilityScore >= 90 ? 'bg-green-600' : article.credibilityScore >= 70 ? 'bg-blue-600' : article.credibilityScore >= 50 ? 'bg-yellow-600' : 'bg-red-600'}`}
                                style={{ width: `${article.credibilityScore}%` }}
                              />
                            </div>
                          </div>
                          {article.sourcesUsed && article.sourcesUsed.length > 0 && (
                            <div className="pt-2 border-t">
                              <p className="text-sm font-semibold mb-1">Sources Used:</p>
                              <div className="flex flex-wrap gap-1">
                                {article.sourcesUsed.map((src, idx) => (
                                  <Badge key={idx} variant="outline" className="text-xs">
                                    {src}
                                  </Badge>
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      </HoverCardContent>
                    </HoverCard>
                  </>
                )}
                <span className="text-sm text-gray-400">•</span>
                <span className="text-sm text-gray-500 flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  {timeAgo(article.publishedAt)}
                </span>
              </div>
              <CardTitle className="text-lg leading-snug mb-2">{article.title}</CardTitle>
              <CardDescription>{article.summaryShort}</CardDescription>
            </div>
            <ImageWithFallback
              src={article.imageUrl}
              alt={article.title}
              className="w-24 h-24 object-cover rounded-md flex-shrink-0"
            />
          </div>
        </CardHeader>
        <CardFooter className="pt-0 pb-4 flex flex-wrap gap-2">
          {article.category.map((cat) => (
            <Badge key={cat} variant="outline" className="text-xs">
              {cat}
            </Badge>
          ))}
          <Button variant="ghost" size="sm" className="ml-auto" asChild>
            <a href={article.url} target="_blank" rel="noopener noreferrer">
              <ExternalLink className="w-4 h-4" />
            </a>
          </Button>
        </CardFooter>
      </Card>
    );
  }

  return (
    <Card className="hover:shadow-lg transition-shadow">
      <ImageWithFallback
        src={article.imageUrl}
        alt={article.title}
        className="w-full h-48 object-cover rounded-t-lg"
      />
      <CardHeader>
        <div className="flex items-center gap-2 mb-2 flex-wrap">
          {article.trending && (
            <Badge variant="default" className="bg-orange-500">
              <TrendingUp className="w-3 h-3 mr-1" />
              Trending
            </Badge>
          )}
          <span className="text-sm text-gray-500">{article.source}</span>
          {article.credibilityScore !== undefined && (
            <>
              <span className="text-sm text-gray-400">•</span>
              <HoverCard>
                <HoverCardTrigger asChild>
                  <span className={`text-sm flex items-center gap-1 cursor-help ${getCredibilityColor(article.credibilityScore)}`}>
                    <Shield className="w-3 h-3" />
                    {article.credibilityScore}%
                  </span>
                </HoverCardTrigger>
                <HoverCardContent className="w-80">
                  <div className="space-y-2">
                    <h4 className="font-semibold flex items-center gap-2">
                      <Shield className="w-4 h-4" />
                      Source Credibility
                    </h4>
                    <div className="space-y-1">
                      <div className="flex items-center justify-between">
                        <span className="text-sm text-gray-600">Reliability:</span>
                        <span className={`text-sm font-semibold ${getCredibilityColor(article.credibilityScore)}`}>
                          {getCredibilityLabel(article.credibilityScore)}
                        </span>
                      </div>
                      <div className="w-full bg-gray-200 h-2 rounded-full overflow-hidden">
                        <div
                          className={`h-full ${article.credibilityScore >= 90 ? 'bg-green-600' : article.credibilityScore >= 70 ? 'bg-blue-600' : article.credibilityScore >= 50 ? 'bg-yellow-600' : 'bg-red-600'}`}
                          style={{ width: `${article.credibilityScore}%` }}
                        />
                      </div>
                    </div>
                    {article.sourcesUsed && article.sourcesUsed.length > 0 && (
                      <div className="pt-2 border-t">
                        <p className="text-sm font-semibold mb-1">Sources Used:</p>
                        <div className="flex flex-wrap gap-1">
                          {article.sourcesUsed.map((src, idx) => (
                            <Badge key={idx} variant="outline" className="text-xs">
                              {src}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </HoverCardContent>
              </HoverCard>
            </>
          )}
          <span className="text-sm text-gray-400">•</span>
          <span className="text-sm text-gray-500 flex items-center gap-1">
            <Clock className="w-3 h-3" />
            {timeAgo(article.publishedAt)}
          </span>
        </div>
        <CardTitle className="text-xl leading-snug">{article.title}</CardTitle>
        <CardDescription className="mt-2">{article.summaryShort}</CardDescription>
      </CardHeader>
      <CardContent>
        {expanded ? (
          <>
            <p className="text-gray-700 mb-4">{article.summaryMedium}</p>
            <div className="bg-gray-50 p-4 rounded-lg">
              <h4 className="font-semibold mb-2">Key Insights</h4>
              <ul className="space-y-1">
                {article.keyInsights.map((insight, idx) => (
                  <li key={idx} className="text-sm text-gray-700 flex items-start gap-2">
                    <span className="text-blue-500 mt-1">•</span>
                    <span>{insight}</span>
                  </li>
                ))}
              </ul>
            </div>
            <Button
              variant="ghost"
              size="sm"
              className="w-full mt-4"
              onClick={() => setExpanded(false)}
            >
              Show Less <ChevronUp className="w-4 h-4 ml-2" />
            </Button>
          </>
        ) : (
          <Button
            variant="ghost"
            size="sm"
            className="w-full"
            onClick={() => setExpanded(true)}
          >
            Read More <ChevronDown className="w-4 h-4 ml-2" />
          </Button>
        )}
      </CardContent>
      <CardFooter className="flex flex-wrap gap-2 border-t pt-4">
        <div className="flex flex-wrap gap-2 flex-1">
          {article.category.map((cat) => (
            <Badge key={cat} variant="outline">
              {cat}
            </Badge>
          ))}
        </div>
        <Button variant="default" size="sm" asChild>
          <a href={article.url} target="_blank" rel="noopener noreferrer">
            Read Full Article <ExternalLink className="w-4 h-4 ml-2" />
          </a>
        </Button>
      </CardFooter>
    </Card>
  );
}
```

#### `/components/ChatInterface.tsx`

```typescript
import { useState } from "react";
import { MessageCircle, Send, Bot, User, Loader2 } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "./ui/card";
import { Input } from "./ui/input";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import { ScrollArea } from "./ui/scroll-area";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  relevantArticles?: Array<{
    id: string;
    title: string;
    summaryShort: string;
  }>;
}

interface ChatInterfaceProps {
  onAskQuestion: (question: string) => Promise<any>;
}

export function ChatInterface({ onAskQuestion }: ChatInterfaceProps) {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "1",
      role: "assistant",
      content: "Hi! I'm your AI tech news assistant. Ask me anything about recent tech news, trends, or specific topics like AI, biotech, or military technology.",
    },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: input,
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);

    try {
      const response = await onAskQuestion(input);

      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: response.answer,
        relevantArticles: response.relevantArticles,
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      console.error("Chat error:", error);
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: "Sorry, I encountered an error processing your question. Please try again.",
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Card className="h-[600px] flex flex-col">
      <CardHeader className="border-b">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 gradient-primary rounded-full flex items-center justify-center shadow-md">
            <MessageCircle className="w-5 h-5 text-white" />
          </div>
          <div>
            <CardTitle>Ask About Tech News</CardTitle>
            <CardDescription>
              Conversational search powered by AI
            </CardDescription>
          </div>
        </div>
      </CardHeader>

      <CardContent className="flex-1 flex flex-col p-0">
        <ScrollArea className="flex-1 p-4">
          <div className="space-y-4">
            {messages.map((message) => (
              <div
                key={message.id}
                className={`flex gap-3 ${
                  message.role === "user" ? "justify-end" : "justify-start"
                }`}
              >
                {message.role === "assistant" && (
                  <div className="w-8 h-8 gradient-primary rounded-full flex items-center justify-center flex-shrink-0 shadow-sm">
                    <Bot className="w-4 h-4 text-white" />
                  </div>
                )}

                <div
                  className={`max-w-[80%] rounded-lg p-3 ${
                    message.role === "user"
                      ? "bg-blue-600 text-white"
                      : "bg-gray-100 text-gray-900"
                  }`}
                >
                  <p className="text-sm whitespace-pre-wrap">{message.content}</p>

                  {message.relevantArticles && message.relevantArticles.length > 0 && (
                    <div className="mt-3 pt-3 border-t border-gray-300 space-y-2">
                      <p className="text-xs text-gray-600 mb-2">
                        Related articles:
                      </p>
                      {message.relevantArticles.map((article) => (
                        <div
                          key={article.id}
                          className="bg-white p-2 rounded text-xs text-gray-800"
                        >
                          <p className="mb-1">{article.title}</p>
                          <p className="text-gray-600">{article.summaryShort}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {message.role === "user" && (
                  <div className="w-8 h-8 bg-gray-300 rounded-full flex items-center justify-center flex-shrink-0">
                    <User className="w-4 h-4 text-gray-600" />
                  </div>
                )}
              </div>
            ))}

            {isLoading && (
              <div className="flex gap-3">
                <div className="w-8 h-8 gradient-primary rounded-full flex items-center justify-center flex-shrink-0 shadow-sm">
                  <Bot className="w-4 h-4 text-white" />
                </div>
                <div className="bg-gray-100 rounded-lg p-3">
                  <Loader2 className="w-4 h-4 animate-spin text-gray-600" />
                </div>
              </div>
            )}
          </div>
        </ScrollArea>

        <div className="border-t p-4">
          <form onSubmit={handleSubmit} className="flex gap-2">
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask me anything about tech news..."
              disabled={isLoading}
              className="flex-1"
            />
            <Button type="submit" disabled={isLoading || !input.trim()}>
              <Send className="w-4 h-4" />
            </Button>
          </form>
          <div className="mt-2 flex flex-wrap gap-2">
            <p className="text-xs text-gray-500 w-full">Try asking:</p>
            <Badge
              variant="outline"
              className="cursor-pointer text-xs hover:bg-gray-100"
              onClick={() => setInput("What's new with OpenAI?")}
            >
              What's new with OpenAI?
            </Badge>
            <Badge
              variant="outline"
              className="cursor-pointer text-xs hover:bg-gray-100"
              onClick={() => setInput("Latest biotech breakthroughs")}
            >
              Latest biotech breakthroughs
            </Badge>
            <Badge
              variant="outline"
              className="cursor-pointer text-xs hover:bg-gray-100"
              onClick={() => setInput("AI safety news this week")}
            >
              AI safety news this week
            </Badge>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
```

#### `/components/ResearchMode.tsx`

_See full file in the repository - includes AI research agent with Markdown
export_

#### `/components/KnowledgeGraph.tsx`

_See full file in the repository - includes interactive canvas visualization_

#### `/components/DigestView.tsx`

_See full file in the repository - includes daily digest UI_

#### `/components/TopicFilter.tsx`

_See full file in the repository - includes preference management_

#### `/components/SearchBar.tsx`

_See full file in the repository - includes search functionality_

### Styles

#### `/styles/globals.css`

```css
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Space+Grotesk:wght@400;500;600;700&display=swap');

@custom-variant dark (&:is(.dark *));

:root {
  --font-size: 16px;
  /* Futuristic Light Theme */
  --background: #f9fafb;
  --foreground: #111827;
  --card: #ffffff;
  --card-foreground: #111827;
  --popover: #ffffff;
  --popover-foreground: #111827;
  --primary: #2563eb;
  --primary-foreground: #ffffff;
  --secondary: #f3f4f6;
  --secondary-foreground: #111827;
  --muted: #f3f4f6;
  --muted-foreground: #6b7280;
  --accent: #eff6ff;
  --accent-foreground: #1e40af;
  --destructive: #dc2626;
  --destructive-foreground: #ffffff;
  --border: #e5e7eb;
  --input: #e5e7eb;
  --input-background: #ffffff;
  --switch-background: #e5e7eb;
  --font-weight-medium: 500;
  --font-weight-normal: 400;
  --ring: #2563eb;
  --chart-1: #3b82f6;
  --chart-2: #8b5cf6;
  --chart-3: #ec4899;
  --chart-4: #f59e0b;
  --chart-5: #10b981;
  --radius: 0.75rem;
  --sidebar: #ffffff;
  --sidebar-foreground: #111827;
  --sidebar-primary: #2563eb;
  --sidebar-primary-foreground: #ffffff;
  --sidebar-accent: #f3f4f6;
  --sidebar-accent-foreground: #111827;
  --sidebar-border: #e5e7eb;
  --sidebar-ring: #2563eb;
}

@theme inline {
  --color-background: var(--background);
  --color-foreground: var(--foreground);
  --color-card: var(--card);
  --color-card-foreground: var(--card-foreground);
  --color-popover: var(--popover);
  --color-popover-foreground: var(--popover-foreground);
  --color-primary: var(--primary);
  --color-primary-foreground: var(--primary-foreground);
  --color-secondary: var(--secondary);
  --color-secondary-foreground: var(--secondary-foreground);
  --color-muted: var(--muted);
  --color-muted-foreground: var(--muted-foreground);
  --color-accent: var(--accent);
  --color-accent-foreground: var(--accent-foreground);
  --color-destructive: var(--destructive);
  --color-destructive-foreground: var(--destructive-foreground);
  --color-border: var(--border);
  --color-input: var(--input);
  --color-input-background: var(--input-background);
  --color-switch-background: var(--switch-background);
  --color-ring: var(--ring);
  --color-chart-1: var(--chart-1);
  --color-chart-2: var(--chart-2);
  --color-chart-3: var(--chart-3);
  --color-chart-4: var(--chart-4);
  --color-chart-5: var(--chart-5);
  --radius-sm: calc(var(--radius) - 4px);
  --radius-md: calc(var(--radius) - 2px);
  --radius-lg: var(--radius);
  --radius-xl: calc(var(--radius) + 4px);
  --color-sidebar: var(--sidebar);
  --color-sidebar-foreground: var(--sidebar-foreground);
  --color-sidebar-primary: var(--sidebar-primary);
  --color-sidebar-primary-foreground: var(--sidebar-primary-foreground);
  --color-sidebar-accent: var(--sidebar-accent);
  --color-sidebar-accent-foreground: var(--sidebar-accent-foreground);
  --color-sidebar-border: var(--sidebar-border);
  --color-sidebar-ring: var(--sidebar-ring);
}

@layer base {
  * {
    @apply border-border outline-ring/50;
  }

  body {
    @apply bg-background text-foreground;
    font-family:
      'Inter',
      -apple-system,
      BlinkMacSystemFont,
      'Segoe UI',
      sans-serif;
  }

  /* Space Grotesk for headings */
  h1,
  h2,
  h3,
  .heading {
    font-family: 'Space Grotesk', 'Inter', sans-serif;
  }
}

/* Futuristic Light Custom Styles */
@layer utilities {
  .glass-card {
    background: rgba(255, 255, 255, 0.8);
    backdrop-filter: blur(10px);
    border: 1px solid rgba(229, 231, 235, 0.6);
    box-shadow:
      0 4px 6px -1px rgba(0, 0, 0, 0.05),
      0 2px 4px -1px rgba(0, 0, 0, 0.03);
  }

  .elevation-sm {
    box-shadow:
      0 1px 3px 0 rgba(0, 0, 0, 0.1),
      0 1px 2px -1px rgba(0, 0, 0, 0.1);
  }

  .elevation-md {
    box-shadow:
      0 4px 6px -1px rgba(0, 0, 0, 0.1),
      0 2px 4px -2px rgba(0, 0, 0, 0.1);
  }

  .elevation-lg {
    box-shadow:
      0 10px 15px -3px rgba(0, 0, 0, 0.1),
      0 4px 6px -4px rgba(0, 0, 0, 0.1);
  }

  .gradient-primary {
    background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%);
  }

  .gradient-accent {
    background: linear-gradient(135deg, #8b5cf6 0%, #6366f1 100%);
  }

  .subtle-pattern {
    background-image:
      radial-gradient(
        circle at 25% 25%,
        rgba(37, 99, 235, 0.02) 0%,
        transparent 50%
      ),
      radial-gradient(
        circle at 75% 75%,
        rgba(139, 92, 246, 0.02) 0%,
        transparent 50%
      );
  }

  .hover-lift {
    transition:
      transform 0.2s ease,
      box-shadow 0.2s ease;
  }

  .hover-lift:hover {
    transform: translateY(-2px);
    box-shadow:
      0 12px 20px -3px rgba(0, 0, 0, 0.12),
      0 6px 8px -4px rgba(0, 0, 0, 0.08);
  }

  .text-gradient {
    background: linear-gradient(135deg, #2563eb 0%, #7c3aed 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }
}

/* Smooth animations */
@keyframes fadeIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.animate-fadeIn {
  animation: fadeIn 0.3s ease-out;
}
```

### Backend Server

#### `/supabase/functions/server/index.tsx`

_Complete Hono server with all API endpoints - see full file in repository_

#### `/utils/supabase/info.tsx`

```typescript
/* Replace with your Supabase credentials */

export const projectId = 'YOUR_PROJECT_ID';
export const publicAnonKey = 'YOUR_ANON_KEY';
```

### Utility Components

#### `/components/figma/ImageWithFallback.tsx`

```typescript
import React, { useState } from 'react'

const ERROR_IMG_SRC =
  'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iODgiIGhlaWdodD0iODgiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyIgc3Ryb2tlPSIjMDAwIiBzdHJva2UtbGluZWpvaW49InJvdW5kIiBvcGFjaXR5PSIuMyIgZmlsbD0ibm9uZSIgc3Ryb2tlLXdpZHRoPSIzLjciPjxyZWN0IHg9IjE2IiB5PSIxNiIgd2lkdGg9IjU2IiBoZWlnaHQ9IjU2IiByeD0iNiIvPjxwYXRoIGQ9Im0xNiA1OCAxNi0xOCAzMiAzMiIvPjxjaXJjbGUgY3g9IjUzIiBjeT0iMzUiIHI9IjciLz48L3N2Zz4KCg=='

export function ImageWithFallback(props: React.ImgHTMLAttributes<HTMLImageElement>) {
  const [didError, setDidError] = useState(false)

  const handleError = () => {
    setDidError(true)
  }

  const { src, alt, style, className, ...rest } = props

  return didError ? (
    <div
      className={`inline-block bg-gray-100 text-center align-middle ${className ?? ''}`}
      style={style}
    >
      <div className="flex items-center justify-center w-full h-full">
        <img src={ERROR_IMG_SRC} alt="Error loading image" {...rest} data-original-url={src} />
      </div>
    </div>
  ) : (
    <img src={src} alt={alt} className={className} style={style} {...rest} onError={handleError} />
  )
}
```

---

## Environment Configuration

### `.env` (Create this file locally)

```env
# Supabase Configuration
SUPABASE_URL=https://YOUR_PROJECT_ID.supabase.co
SUPABASE_ANON_KEY=your_anon_key_here
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key_here

# Optional: For production deployment
VITE_SUPABASE_URL=${SUPABASE_URL}
VITE_SUPABASE_ANON_KEY=${SUPABASE_ANON_KEY}
```

---

## Package Dependencies

### Full `package.json` with all dependencies:

```json
{
  "name": "techpulse-ai",
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "lint": "eslint .",
    "deploy": "npm run build && supabase functions deploy make-server-3889d4d6"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "lucide-react": "latest",
    "sonner": "^2.0.3",
    "@radix-ui/react-slot": "^1.1.2",
    "@radix-ui/react-dialog": "latest",
    "@radix-ui/react-popover": "latest",
    "@radix-ui/react-checkbox": "latest",
    "@radix-ui/react-label": "latest",
    "@radix-ui/react-separator": "latest",
    "@radix-ui/react-tabs": "latest",
    "@radix-ui/react-scroll-area": "latest",
    "@radix-ui/react-select": "latest",
    "@radix-ui/react-switch": "latest",
    "@radix-ui/react-textarea": "latest",
    "@radix-ui/react-hover-card": "latest",
    "@radix-ui/react-accordion": "latest",
    "@radix-ui/react-alert-dialog": "latest",
    "@radix-ui/react-avatar": "latest",
    "@radix-ui/react-collapsible": "latest",
    "@radix-ui/react-context-menu": "latest",
    "@radix-ui/react-dropdown-menu": "latest",
    "@radix-ui/react-menubar": "latest",
    "@radix-ui/react-navigation-menu": "latest",
    "@radix-ui/react-progress": "latest",
    "@radix-ui/react-radio-group": "latest",
    "@radix-ui/react-slider": "latest",
    "@radix-ui/react-tooltip": "latest",
    "@radix-ui/react-toggle": "latest",
    "@radix-ui/react-toggle-group": "latest",
    "class-variance-authority": "^0.7.1",
    "clsx": "latest",
    "tailwind-merge": "latest",
    "date-fns": "latest",
    "react-day-picker": "latest"
  },
  "devDependencies": {
    "@types/react": "^18.3.1",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.0",
    "vite": "^5.2.0",
    "typescript": "^5.4.5",
    "tailwindcss": "^4.0.0",
    "autoprefixer": "^10.4.19",
    "postcss": "^8.4.38",
    "eslint": "^8.57.0"
  }
}
```

---

## Features

### 1. News Feed

- Multi-source news aggregation
- Topic-based filtering (10 categories)
- Search functionality
- Trending articles
- Compact/detailed view modes
- Source credibility scores (70-100%)
- Real-time updates

### 2. Research Mode

- AI-powered research queries
- Multi-article analysis
- Markdown export
- Key findings extraction
- Trending topic identification
- Source credibility analysis

### 3. Knowledge Graph

- Interactive canvas visualization
- Force-directed graph layout
- Company/person/technology nodes
- Relationship mapping
- Click-to-explore
- Zoom controls

### 4. Daily Digest

- Top stories compilation
- Category breakdown charts
- Trending topics
- Email subscription CTA
- Personalized content

### 5. Ask AI

- Conversational Q&A interface
- Context-aware responses
- Related articles
- Suggested questions
- Real-time chat

### 6. Settings

- Topic preferences
- Visual feedback (unsaved changes badge)
- Loading states
- Toast notifications
- Success indicators

---

## Deployment

### Deploy to Vercel

```bash
# Install Vercel CLI
npm i -g vercel

# Deploy
vercel
```

### Deploy to Netlify

```bash
# Install Netlify CLI
npm i -g netlify-cli

# Build and deploy
npm run build
netlify deploy --prod
```

### Deploy Supabase Edge Functions

```bash
# Deploy the server
supabase functions deploy make-server-3889d4d6

# Set environment variables
supabase secrets set SUPABASE_URL=your_url
supabase secrets set SUPABASE_SERVICE_ROLE_KEY=your_key
```

---

## Next Steps

1. **Add Real News Sources**: Integrate NewsAPI, RSS feeds, or web scraping
2. **Implement AI**: Connect OpenAI/Claude for real summarization
3. **Add Authentication**: Implement Supabase Auth for user accounts
4. **Email Digests**: Set up automated email delivery
5. **Mobile App**: Build React Native version
6. **Analytics**: Add usage tracking
7. **Bookmarking**: Save favorite articles
8. **Sharing**: Social media integration
9. **Dark Mode**: Add theme toggle
10. **Performance**: Implement pagination and lazy loading

---

## License

MIT

---

## Support

For questions or issues, please open an issue on GitHub or contact the
development team.

---

**Generated by TechPulse AI Export Tool**  
**Date:** October 17, 2025
