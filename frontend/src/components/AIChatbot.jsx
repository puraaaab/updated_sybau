import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';

// ---- Config -----------------------------------------------------------------

const SESSION_STORAGE_KEY = 'vms_chat_session_id';
const MAX_IMAGE_BYTES = 15 * 1024 * 1024;
const ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp'];
const NEAR_BOTTOM_THRESHOLD_PX = 120;
const AI_NAME = 'Sybau AI';

// ---- Dynamic Greeting Helper ----

function getDynamicGreeting() {
  const hour = new Date().getHours();
  let timeStr = 'Good Day';
  if (hour >= 5 && hour < 12) timeStr = 'Good Morning';
  else if (hour >= 12 && hour < 17) timeStr = 'Good Afternoon';
  else if (hour >= 17 && hour < 22) timeStr = 'Good Evening';
  else timeStr = 'Late Night Security Operations';
  return `${timeStr}, Officer! 👋`;
}

// ---- Tiny markdown-lite renderer (bold / italic only) ----

function renderInline(text, keyPrefix) {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g).filter(Boolean);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={`${keyPrefix}-${i}`} className="font-semibold text-cyan-300">{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith('*') && part.endsWith('*')) {
      return <em key={`${keyPrefix}-${i}`} className="italic text-slate-300">{part.slice(1, -1)}</em>;
    }
    return <React.Fragment key={`${keyPrefix}-${i}`}>{part}</React.Fragment>;
  });
}

function MessageText({ text }) {
  return (
    <div className="whitespace-pre-wrap font-sans text-xs sm:text-sm leading-relaxed">
      {text.split('\n').map((line, idx) => (
        <p key={idx} className={idx > 0 ? 'mt-1.5' : ''}>
          {line ? renderInline(line, idx) : '\u00A0'}
        </p>
      ))}
    </div>
  );
}

// ---- Helpers ------------------------------------------------------------------

function nowLabel() {
  return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function loadOrCreateSessionId() {
  try {
    const existing = window.localStorage.getItem(SESSION_STORAGE_KEY);
    if (existing) return existing;
  } catch {
    // localStorage unavailable
  }
  const fresh = `chat_${Math.random().toString(36).substring(2, 9)}`;
  try { window.localStorage.setItem(SESSION_STORAGE_KEY, fresh); } catch { /* ignore */ }
  return fresh;
}

// ---- Draggable Hook with Smooth Movement & Bounds Padding --------------------

function useDraggable(initialPos) {
  const [pos, setPos] = useState(initialPos);
  const [isDraggingState, setIsDraggingState] = useState(false);
  const dragRef = useRef(null);
  const isDragging = useRef(false);
  const startOffset = useRef({ x: 0, y: 0 });

  const onMouseDown = useCallback((e) => {
    if (e.target.closest('button') || e.target.closest('input')) return;
    isDragging.current = true;
    setIsDraggingState(true);
    startOffset.current = {
      x: e.clientX - pos.x,
      y: e.clientY - pos.y,
    };
    e.preventDefault();
  }, [pos]);

  useEffect(() => {
    const onMouseMove = (e) => {
      if (!isDragging.current) return;
      const windowWidth = window.innerWidth;
      const windowHeight = window.innerHeight;
      
      const newX = Math.max(10, Math.min(windowWidth - 360, e.clientX - startOffset.current.x));
      const newY = Math.max(10, Math.min(windowHeight - 80, e.clientY - startOffset.current.y));
      setPos({ x: newX, y: newY });
    };

    const onMouseUp = () => {
      isDragging.current = false;
      setIsDraggingState(false);
    };

    window.addEventListener('mousemove', onMouseMove);
    window.addEventListener('mouseup', onMouseUp);
    return () => {
      window.removeEventListener('mousemove', onMouseMove);
      window.removeEventListener('mouseup', onMouseUp);
    };
  }, []);

  return { pos, setPos, onMouseDown, dragRef, isDragging: isDraggingState };
}

// ---- Main Component ----------------------------------------------------------

export default function AIChatbot() {
  const [isOpen, setIsOpen] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [sessionId] = useState(loadOrCreateSessionId);
  const [messages, setMessages] = useState([]);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [inputQuery, setInputQuery] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);
  const [imagePreview, setImagePreview] = useState(null);
  const [imageError, setImageError] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [suggestions, setSuggestions] = useState([
    'Koi blue color ka shirt wala banda station pr dikha tha kya?',
    'Laal color ki car spot hui kya gate ke paas?',
    'Bina helmet motorcycle chalane wala koi mila?',
    'Show me suspicious crowd activity near central bus depo'
  ]);
  const [previewSnapshot, setPreviewSnapshot] = useState(null);
  const [lastFailedPayload, setLastFailedPayload] = useState(null);

  const messagesEndRef = useRef(null);
  const scrollContainerRef = useRef(null);
  const fileInputRef = useRef(null);
  const inputRef = useRef(null);
  const abortControllerRef = useRef(null);
  const stickToBottomRef = useRef(true);

  // Default position bottom-right
  const defaultPos = useMemo(() => ({
    x: Math.max(20, window.innerWidth - 480),
    y: Math.max(20, window.innerHeight - 710)
  }), []);

  const { pos, setPos, onMouseDown, isDragging } = useDraggable(defaultPos);

  // ---- Scroll Management ----

  const handleScroll = useCallback(() => {
    const el = scrollContainerRef.current;
    if (!el) return;
    stickToBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_THRESHOLD_PX;
  }, []);

  useEffect(() => {
    if (isOpen && stickToBottomRef.current) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, isOpen, isLoading]);

  // Focus input when opened
  useEffect(() => {
    if (isOpen) {
      setUnreadCount(0);
      const t = setTimeout(() => inputRef.current?.focus(), 150);
      return () => clearTimeout(t);
    }
  }, [isOpen]);

  useEffect(() => {
    function onKeyDown(e) {
      if (e.key === 'Escape' && isOpen) setIsOpen(false);
    }
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [isOpen]);

  // ---- Fetch Quick Suggestions ----

  useEffect(() => {
    fetch('/api/v1/chat/suggestions')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => { if (data?.suggestions?.length) setSuggestions(data.suggestions); })
      .catch(() => { });
  }, []);

  // ---- Load Session History ----

  useEffect(() => {
    if (!isOpen || historyLoaded) return;
    setHistoryLoaded(true);
    setHistoryLoading(true);
    fetch(`/api/v1/chat/history?session_id=${encodeURIComponent(sessionId)}&limit=50`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        const restored = data?.messages || [];
        if (restored.length > 0) {
          setMessages(restored.map((m) => ({
            id: `hist_${m.id}`,
            sender: m.sender,
            text: m.text,
            image_url: m.image_url || null,
            timeline: m.timeline || [],
            trajectory: m.trajectory || null,
            candidates: m.candidates || [],
            timestamp: m.timestamp
              ? new Date(m.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
              : nowLabel(),
          })));
        }
      })
      .catch(() => { })
      .finally(() => setHistoryLoading(false));
  }, [isOpen, historyLoaded, sessionId]);

  useEffect(() => { return () => abortControllerRef.current?.abort(); }, []);

  // ---- File Attachment Handling ----

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setImageError(null);
    if (!ALLOWED_IMAGE_TYPES.includes(file.type)) {
      setImageError('Unsupported format — please use JPG, PNG, or WEBP.');
      e.target.value = '';
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      setImageError(`Image is too large (max ${Math.round(MAX_IMAGE_BYTES / (1024 * 1024))}MB).`);
      e.target.value = '';
      return;
    }
    setSelectedFile(file);
    const reader = new FileReader();
    reader.onloadend = () => setImagePreview(reader.result);
    reader.onerror = () => setImageError('Could not read file — try another image.');
    reader.readAsDataURL(file);
  };

  const clearSelectedFile = () => {
    setSelectedFile(null);
    setImagePreview(null);
    setImageError(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  // ---- Message Dispatch ----

  const handleSend = async (queryText = inputQuery, retryFile = null) => {
    const textToSend = (typeof queryText === 'string' ? queryText : inputQuery).trim();
    const fileToSend = retryFile ?? selectedFile;
    if (!textToSend && !fileToSend) return;

    abortControllerRef.current?.abort();
    const controller = new AbortController();
    abortControllerRef.current = controller;

    const userMessageId = `usr_${Date.now()}`;
    if (!retryFile) {
      setMessages((prev) => [
        ...prev,
        { id: userMessageId, sender: 'user', text: textToSend, image_url: imagePreview, timestamp: nowLabel() },
      ]);
    }
    setInputQuery('');
    clearSelectedFile();
    setIsLoading(true);
    setLastFailedPayload(null);

    try {
      let resp;
      if (fileToSend) {
        const formData = new FormData();
        formData.append('file', fileToSend);
        if (textToSend) formData.append('query', textToSend);
        formData.append('session_id', sessionId);
        resp = await fetch('/api/v1/chat/upload-search', { method: 'POST', body: formData, signal: controller.signal });
      } else {
        resp = await fetch('/api/v1/chat/message', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: textToSend, session_id: sessionId }),
          signal: controller.signal,
        });
      }

      if (!resp.ok) throw new Error(`Server responded ${resp.status}`);
      const resData = await resp.json();

      const botMsg = {
        id: `bot_${Date.now()}`,
        sender: 'assistant',
        text: resData.text || 'No matches found across active camera streams.',
        timeline: resData.timeline || [],
        trajectory: resData.trajectory || null,
        candidates: resData.candidates || [],
        timestamp: nowLabel(),
      };
      setMessages((prev) => [...prev, botMsg]);
      if (!isOpen) setUnreadCount((c) => c + 1);
    } catch (err) {
      if (err.name === 'AbortError') return;
      setLastFailedPayload({ text: textToSend, file: fileToSend });
      setMessages((prev) => [
        ...prev,
        {
          id: `err_${Date.now()}`,
          sender: 'assistant',
          isError: true,
          text: `⚠️ **Couldn't connect to ${AI_NAME}.** (${err.message})`,
          timeline: [],
          timestamp: nowLabel(),
        },
      ]);
      if (!isOpen) setUnreadCount((c) => c + 1);
    } finally {
      setIsLoading(false);
    }
  };

  const handleRetry = () => {
    if (!lastFailedPayload) return;
    handleSend(lastFailedPayload.text, lastFailedPayload.file);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  const startNewChat = () => {
    abortControllerRef.current?.abort();
    const fresh = `chat_${Math.random().toString(36).substring(2, 9)}`;
    try { window.localStorage.setItem(SESSION_STORAGE_KEY, fresh); } catch { /* ignore */ }
    setMessages([]);
    setHistoryLoaded(false);
  };

  const unreadBadge = useMemo(() => (unreadCount > 9 ? '9+' : String(unreadCount)), [unreadCount]);

  const windowW = isExpanded ? Math.min(window.innerWidth - 40, 880) : 460;
  const windowH = isExpanded ? Math.min(window.innerHeight - 40, 780) : 660;

  return (
    <>
      {/* ── Floating Launcher Trigger Orb (Collapsed state) ──────────────── */}
      {!isOpen && (
        <button
          onClick={() => setIsOpen(true)}
          style={{ position: 'fixed', bottom: 28, right: 28, zIndex: 9999 }}
          className="group relative flex items-center gap-3 px-4 py-3.5 rounded-2xl bg-gradient-to-r from-slate-950 via-slate-900 to-indigo-950 border border-cyan-500/40 shadow-[0_0_30px_rgba(6,182,212,0.35)] hover:shadow-[0_0_45px_rgba(6,182,212,0.6)] hover:border-cyan-400/80 hover:scale-105 active:scale-95 transition-all duration-300"
          title={`Launch ${AI_NAME} Copilot`}
          aria-label={`Launch ${AI_NAME} Copilot`}
        >
          {/* Pulsing ring aura */}
          <span className="absolute -inset-1 rounded-2xl bg-gradient-to-r from-cyan-500 via-indigo-500 to-emerald-500 opacity-20 blur-md group-hover:opacity-60 transition duration-500 animate-pulse" />

          {/* AI Avatar Orb */}
          <div className="relative w-9 h-9 rounded-xl bg-gradient-to-tr from-cyan-500 via-indigo-600 to-emerald-400 p-[1.5px] shadow-lg shadow-cyan-500/30">
            <div className="w-full h-full bg-slate-950 rounded-[10px] flex items-center justify-center">
              <svg className="w-5 h-5 text-cyan-400 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
            </div>
            <span className="absolute -bottom-0.5 -right-0.5 w-3 h-3 rounded-full bg-emerald-400 border-2 border-slate-950 shadow-sm shadow-emerald-400" />
          </div>

          <div className="text-left hidden sm:block">
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-black tracking-wider text-slate-100 uppercase">{AI_NAME}</span>
              <span className="text-[9px] font-bold px-1.5 py-0.2 rounded bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">LIVE RAG</span>
            </div>
            <p className="text-[10px] font-medium text-slate-400">Ask surveillance copilot…</p>
          </div>

          {/* Unread badge */}
          {unreadCount > 0 && (
            <span className="absolute -top-2 -right-2 min-w-[22px] h-5 px-1.5 rounded-full bg-red-500 text-white text-[10px] font-black flex items-center justify-center border-2 border-slate-950 shadow-lg animate-bounce">
              {unreadBadge}
            </span>
          )}
        </button>
      )}

      {/* ── Floating AI Chat Modal ────────────────────────────────────────── */}
      {isOpen && (
        <div
          role="dialog"
          aria-label={`${AI_NAME} Surveillance Copilot`}
          style={{
            position: 'fixed',
            zIndex: 9999,
            left: isExpanded ? 20 : pos.x,
            top: isExpanded ? 20 : pos.y,
            width: isExpanded ? `calc(100vw - 40px)` : `${windowW}px`,
            height: isExpanded ? `calc(100vh - 40px)` : `${windowH}px`,
            maxHeight: '96vh',
            transition: isDragging ? 'none' : 'all 0.25s cubic-bezier(0.16, 1, 0.3, 1)',
            display: 'flex',
            flexDirection: 'column',
          }}
          className={`bg-slate-950/95 backdrop-blur-3xl border border-slate-700/80 shadow-[0_25px_70px_-15px_rgba(0,0,0,0.9)] rounded-3xl overflow-hidden ${
            isDragging ? 'ring-2 ring-cyan-500/80 shadow-cyan-500/20' : 'hover:border-slate-600/90'
          }`}
        >
          {/* Cybernetic Tech Grid Background Pattern overlay */}
          <div 
            className="absolute inset-0 pointer-events-none opacity-[0.035]"
            style={{
              backgroundImage: `radial-gradient(circle at 1px 1px, rgba(255,255,255,0.8) 1px, transparent 0)`,
              backgroundSize: '24px 24px'
            }}
          />

          {/* Neon Glow Accents */}
          <div className="absolute -top-24 -left-24 w-60 h-60 bg-cyan-500/15 rounded-full blur-3xl pointer-events-none" />
          <div className="absolute -bottom-24 -right-24 w-60 h-60 bg-indigo-500/15 rounded-full blur-3xl pointer-events-none" />

          {/* ── Header & Drag Bar ───────────────────────────────────────── */}
          <div
            onMouseDown={onMouseDown}
            style={{ cursor: isExpanded ? 'default' : (isDragging ? 'grabbing' : 'grab'), userSelect: 'none' }}
            className="relative px-5 py-3.5 bg-gradient-to-r from-slate-900/95 via-slate-900/90 to-indigo-950/90 border-b border-slate-800/90 flex items-center justify-between flex-shrink-0"
          >
            <div className="flex items-center gap-3.5">
              {/* Animated Avatar */}
              <div className="relative w-10 h-10 rounded-2xl bg-gradient-to-tr from-cyan-400 via-indigo-500 to-emerald-400 p-[1.5px] shadow-lg shadow-cyan-500/20">
                <div className="w-full h-full bg-slate-950 rounded-[14px] flex items-center justify-center">
                  <svg className="w-5 h-5 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                </div>
                <span className="absolute bottom-0 right-0 w-3 h-3 rounded-full bg-emerald-400 border-2 border-slate-950 shadow-sm shadow-emerald-400 animate-pulse" />
              </div>

              <div>
                <div className="flex items-center gap-2">
                  <h3 className="text-sm font-black text-slate-100 tracking-wide flex items-center gap-1.5">
                    {AI_NAME}
                  </h3>
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[9px] font-extrabold bg-cyan-500/15 text-cyan-300 border border-cyan-500/30">
                    <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-ping" />
                    LIVE MULTI-CAMERA RAG
                  </span>
                </div>
                <p className="text-[11px] font-medium text-slate-400 mt-0.5">Autonomous Forensic Intelligence Assistant</p>
              </div>
            </div>

            {/* Header Action Buttons */}
            <div className="flex items-center gap-1.5">
              {/* Clear / New Session */}
              <button
                onClick={startNewChat}
                className="p-2 text-slate-400 hover:text-slate-100 hover:bg-slate-800/80 rounded-xl border border-transparent hover:border-slate-700/60 transition-all"
                title="New Chat Session"
                aria-label="New Chat Session"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" />
                </svg>
              </button>

              {/* Expand / Restore */}
              <button
                onClick={() => setIsExpanded(!isExpanded)}
                className="p-2 text-slate-400 hover:text-slate-100 hover:bg-slate-800/80 rounded-xl border border-transparent hover:border-slate-700/60 transition-all"
                title={isExpanded ? 'Restore Size' : 'Maximize Window'}
                aria-label={isExpanded ? 'Restore Window Size' : 'Maximize Window'}
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  {isExpanded ? (
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"
                      d="M9 9L4 4m0 0l5 0m-5 0l0 5m11 5l5 5m0 0l-5 0m5 0l0-5" />
                  ) : (
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"
                      d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4" />
                  )}
                </svg>
              </button>

              {/* Minimize / Close */}
              <button
                onClick={() => setIsOpen(false)}
                className="p-2 text-slate-400 hover:text-red-400 hover:bg-slate-800/80 rounded-xl border border-transparent hover:border-slate-700/60 transition-all"
                title="Minimize Chat"
                aria-label="Minimize Chat"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
                </svg>
              </button>
            </div>
          </div>

          {/* ── Interactive Prompt Suggestions Bar ──────────────────────────── */}
          <div className="px-4 py-2 bg-slate-900/60 border-b border-slate-800/80 flex items-center gap-2 overflow-x-auto scrollbar-none flex-shrink-0">
            <span className="text-[10px] font-bold uppercase tracking-wider text-cyan-400 shrink-0 flex items-center gap-1">
              ⚡ Quick Prompt:
            </span>
            {suggestions.map((sug, i) => (
              <button
                key={i}
                onClick={() => handleSend(sug)}
                className="shrink-0 text-[11px] font-medium px-3 py-1 rounded-full bg-slate-900/90 hover:bg-cyan-500/20 text-slate-300 hover:text-cyan-200 border border-slate-700/80 hover:border-cyan-500/50 transition-all duration-200"
              >
                {sug.length > 45 ? sug.slice(0, 45) + '…' : sug}
              </button>
            ))}
          </div>

          {/* ── Messages Scroll Area ──────────────────────────────────────── */}
          <div
            ref={scrollContainerRef}
            onScroll={handleScroll}
            className="flex-1 overflow-y-auto px-5 py-5 space-y-5 scrollbar-thin scrollbar-track-slate-950 scrollbar-thumb-slate-800"
          >
            {/* Dynamic Welcome Greeting Banner (when chat is clean or loading) */}
            {messages.length === 0 && !historyLoading && (
              <div className="relative p-5 rounded-2xl bg-gradient-to-br from-slate-900/90 via-indigo-950/40 to-slate-900/90 border border-cyan-500/30 text-slate-200 shadow-xl overflow-hidden">
                <div className="absolute top-0 right-0 p-4 opacity-10 pointer-events-none">
                  <svg className="w-24 h-24 text-cyan-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="1" d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                </div>
                
                <div className="flex items-center gap-3 mb-3">
                  <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-500 to-indigo-600 flex items-center justify-center text-white shadow-md shadow-cyan-500/20">
                    <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M14.828 14.828a4 4 0 01-5.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  </div>
                  <div>
                    <h4 className="text-sm font-black text-cyan-300">{getDynamicGreeting()}</h4>
                    <p className="text-[11px] font-medium text-slate-400">Ask natural queries across all city camera streams in English, Hinglish, or Gujlish.</p>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 mt-4">
                  <button
                    onClick={() => handleSend('Koi blue color ka shirt wala banda station pr dikha tha kya?')}
                    className="p-2.5 rounded-xl bg-slate-900/80 hover:bg-cyan-500/20 border border-slate-700/80 hover:border-cyan-500/40 text-left transition-all group"
                  >
                    <span className="text-[10px] font-bold text-cyan-400 block group-hover:text-cyan-300">👤 Person Search</span>
                    <span className="text-xs text-slate-300 font-medium">"Blue shirt at railway station"</span>
                  </button>

                  <button
                    onClick={() => handleSend('Laal color ki car spot hui kya gate ke paas?')}
                    className="p-2.5 rounded-xl bg-slate-900/80 hover:bg-cyan-500/20 border border-slate-700/80 hover:border-cyan-500/40 text-left transition-all group"
                  >
                    <span className="text-[10px] font-bold text-emerald-400 block group-hover:text-emerald-300">🚗 Vehicle Lookup</span>
                    <span className="text-xs text-slate-300 font-medium">"Red car near entrance gate"</span>
                  </button>

                  <button
                    onClick={() => handleSend('Bina helmet motorcycle chalane wala koi mila?')}
                    className="p-2.5 rounded-xl bg-slate-900/80 hover:bg-cyan-500/20 border border-slate-700/80 hover:border-cyan-500/40 text-left transition-all group"
                  >
                    <span className="text-[10px] font-bold text-amber-400 block group-hover:text-amber-300">🚨 Traffic Violation</span>
                    <span className="text-xs text-slate-300 font-medium">"Rider without helmet"</span>
                  </button>

                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="p-2.5 rounded-xl bg-slate-900/80 hover:bg-cyan-500/20 border border-slate-700/80 hover:border-cyan-500/40 text-left transition-all group"
                  >
                    <span className="text-[10px] font-bold text-purple-400 block group-hover:text-purple-300">📷 Vision Match</span>
                    <span className="text-xs text-slate-300 font-medium">"Upload target photo to scan"</span>
                  </button>
                </div>
              </div>
            )}

            {historyLoading && (
              <div className="flex justify-center py-4">
                <span className="text-[11px] font-semibold text-cyan-400 italic animate-pulse">Loading previous security logs…</span>
              </div>
            )}

            {messages.map((msg) => (
              <div key={msg.id} className={`flex flex-col ${msg.sender === 'user' ? 'items-end' : 'items-start'}`}>
                <div className={`max-w-[88%] p-4 rounded-2xl text-xs sm:text-sm leading-relaxed border shadow-md transition-all ${
                  msg.sender === 'user'
                    ? 'bg-gradient-to-br from-cyan-600/90 to-indigo-700/90 border-cyan-400/40 text-white rounded-br-none shadow-cyan-600/20'
                    : msg.isError
                      ? 'bg-red-950/40 border-red-700/60 text-red-300 rounded-bl-none'
                      : 'bg-slate-900/95 border-slate-800/90 text-slate-200 rounded-bl-none shadow-black/40'
                }`}>
                  {/* User-attached image thumbnail */}
                  {msg.image_url && (
                    <img
                      src={msg.image_url}
                      alt="Uploaded target"
                      className="mb-2.5 rounded-xl w-full max-h-48 object-cover border border-cyan-500/50 cursor-pointer shadow-md"
                      onClick={() => setPreviewSnapshot(msg.image_url)}
                    />
                  )}

                  {/* Assistant Avatar & Name Tag */}
                  {msg.sender === 'assistant' && !msg.isError && (
                    <div className="flex items-center gap-1.5 mb-2 pb-1.5 border-b border-slate-800/80">
                      <span className="w-2 h-2 rounded-full bg-cyan-400 shadow-sm shadow-cyan-400" />
                      <span className="text-[11px] font-black text-cyan-400 uppercase tracking-wider">{AI_NAME}</span>
                    </div>
                  )}

                  <MessageText text={msg.text} />

                  {/* Retry Action */}
                  {msg.isError && lastFailedPayload && (
                    <button
                      onClick={handleRetry}
                      className="mt-2.5 inline-flex items-center gap-1 px-3 py-1 rounded-lg bg-red-900/60 hover:bg-red-800/80 text-red-200 font-bold text-xs border border-red-700/60 transition-all"
                    >
                      🔄 Retry Request
                    </button>
                  )}

                  {/* Evidence Timeline Cards */}
                  {msg.timeline && msg.timeline.length > 0 && (
                    <div className="mt-3.5 pt-3 border-t border-slate-800/80 space-y-2.5">
                      <div className="text-[10px] font-black text-cyan-400 tracking-widest uppercase flex items-center justify-between">
                        <span>📍 Evidence Trail ({msg.timeline.length} Detections)</span>
                      </div>
                      {msg.timeline.map((item, tIdx) => (
                        <div key={tIdx} className="flex gap-3 items-center p-2 rounded-xl bg-slate-950/80 border border-slate-800/80 hover:border-cyan-500/40 transition-all">
                          {item.snapshot_url ? (
                            <img
                              src={item.snapshot_url}
                              alt="Snapshot"
                              className="w-16 h-11 rounded-lg object-cover border border-slate-700 cursor-pointer shrink-0 hover:scale-105 transition-transform"
                              onClick={() => setPreviewSnapshot(item.snapshot_url)}
                            />
                          ) : (
                            <div className="w-16 h-11 rounded-lg bg-slate-900 border border-slate-800 flex items-center justify-center text-slate-500 shrink-0 text-xs font-bold">📷 NO PIC</div>
                          )}
                          <div className="flex-1 min-w-0">
                            <p className="text-xs font-bold text-slate-100 truncate">{item.camera_name}</p>
                            <p className="text-[10px] text-slate-400 font-medium">{item.time_display}</p>
                            {item.confidence != null && (
                              <div className="mt-1.5 h-1.5 rounded-full bg-slate-800 overflow-hidden w-full">
                                <div
                                  className="h-full rounded-full bg-gradient-to-r from-cyan-400 to-emerald-400"
                                  style={{ width: `${Math.round(item.confidence * 100)}%` }}
                                />
                              </div>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Trajectory Route */}
                  {msg.trajectory && (
                    <div className="mt-3.5 pt-3 border-t border-slate-800/80 space-y-2">
                      <div className="text-[10px] font-black text-emerald-400 tracking-widest uppercase flex items-center justify-between">
                        <span>🗺️ Inferred Trajectory Path</span>
                        {msg.trajectory.confidence && (
                          <span className="text-[10px] font-bold text-slate-400">Match {Math.round(msg.trajectory.confidence * 100)}%</span>
                        )}
                      </div>
                      {msg.trajectory.legs?.map((leg, lIdx) => (
                        <div key={lIdx} className="flex items-center gap-2 text-[11px] font-medium text-slate-300 flex-wrap bg-slate-950/60 p-2 rounded-xl border border-slate-800/80">
                          <span className="font-bold text-cyan-300">{leg.from_camera}</span>
                          <span className="text-slate-500">➔</span>
                          <span className="font-bold text-cyan-300">{leg.to_camera}</span>
                          {leg.gap_minutes != null && <span className="text-slate-400 font-normal">({leg.gap_minutes} min gap)</span>}
                          {leg.inferred_speed_kmh != null && <span className="text-emerald-400 font-bold">· ~{leg.inferred_speed_kmh} km/h</span>}
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Candidate Disambiguation Cards */}
                  {msg.candidates && msg.candidates.length > 0 && (
                    <div className="mt-3.5 pt-3 border-t border-slate-800/80 space-y-2">
                      <div className="text-[10px] font-black text-amber-400 tracking-widest uppercase flex items-center justify-between">
                        <span>🔍 Select Target Candidate</span>
                        <span className="text-[10px] text-slate-400 font-normal">{msg.candidates.length} Options</span>
                      </div>
                      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                        {msg.candidates.map((cand) => (
                          <div key={cand.candidate_id} className="p-2.5 bg-slate-950/90 rounded-xl border border-slate-800 flex flex-col justify-between text-xs">
                            <div className="flex items-center gap-2.5 mb-2">
                              {cand.snapshot_url
                                ? <img src={cand.snapshot_url} alt="Candidate" className="w-12 h-12 rounded-lg object-cover border border-slate-700 shrink-0" />
                                : <div className="w-12 h-12 rounded-lg bg-slate-900 border border-slate-800 flex items-center justify-center text-slate-500 shrink-0">📷</div>
                              }
                              <div className="min-w-0 flex-1">
                                <p className="font-bold text-slate-100 truncate">{cand.title}</p>
                                <p className="text-[10px] text-slate-400 truncate">{cand.camera_name} ({cand.time_display})</p>
                              </div>
                            </div>
                            <button
                              onClick={() => handleSend(`Show route for Candidate #${cand.candidate_id}`)}
                              className="w-full py-1.5 px-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-[11px] flex items-center justify-center gap-1 transition-all shadow-md"
                            >
                              🗺️ Trace Full Route
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
                <span className="text-[10px] font-medium text-slate-500 mt-1 px-1">{msg.timestamp}</span>
              </div>
            ))}

            {/* Active AI Processing Indicator */}
            {isLoading && (
              <div className="flex flex-col items-start">
                <div className="p-4 rounded-2xl bg-slate-900/95 border border-cyan-500/40 text-slate-200 text-xs flex items-center gap-3 shadow-lg shadow-cyan-500/10">
                  <div className="flex items-center gap-1.5">
                    <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 animate-bounce" />
                    <span className="w-2.5 h-2.5 rounded-full bg-indigo-400 animate-bounce [animation-delay:0.2s]" />
                    <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-bounce [animation-delay:0.4s]" />
                  </div>
                  <span className="text-cyan-300 font-semibold italic">{AI_NAME} is searching live vector memory & video feeds…</span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* ── Image Attachment Bar ──────────────────────────────────────── */}
          {(imagePreview || imageError) && (
            <div className="px-4 py-2.5 bg-slate-900/90 border-t border-slate-800/80 flex items-center justify-between flex-shrink-0">
              <div className="flex items-center gap-3">
                {imagePreview && (
                  <img src={imagePreview} alt="Target Preview" className="w-11 h-11 rounded-xl object-cover border border-cyan-500 shadow-md" />
                )}
                <div>
                  {imageError
                    ? <p className="text-xs font-bold text-red-400">{imageError}</p>
                    : <>
                        <p className="text-xs font-bold text-slate-100">Target Image Attached</p>
                        <p className="text-[10px] font-medium text-cyan-400">Cross-camera vision matching active</p>
                      </>
                  }
                </div>
              </div>
              <button onClick={clearSelectedFile} className="text-slate-400 hover:text-red-400 p-1 text-xs font-bold" title="Remove Attachment">✕</button>
            </div>
          )}

          {/* ── Chat Input Bar ────────────────────────────────────────────── */}
          <div className="p-3.5 bg-slate-900/95 border-t border-slate-800/90 flex items-center gap-2.5 flex-shrink-0">
            <input type="file" ref={fileInputRef} onChange={handleFileChange} accept="image/jpeg,image/png,image/webp" className="hidden" />

            <button
              onClick={() => fileInputRef.current?.click()}
              className="p-3 text-slate-400 hover:text-cyan-300 hover:bg-slate-800/90 rounded-2xl border border-slate-800 hover:border-cyan-500/50 transition-all shrink-0"
              title="Upload image to match target"
              aria-label="Upload image to match target"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"
                  d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
            </button>

            <input
              ref={inputRef}
              type="text"
              value={inputQuery}
              onChange={(e) => setInputQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={`Ask ${AI_NAME} anything… (English, Hinglish, Gujlish ok!)`}
              aria-label="Message Query"
              className="flex-1 bg-slate-950/90 text-slate-100 text-xs sm:text-sm px-4 py-3 rounded-2xl border border-slate-800 focus:outline-none focus:border-cyan-500/80 transition-all placeholder:text-slate-500"
            />

            <button
              onClick={() => handleSend()}
              disabled={isLoading || (!inputQuery.trim() && !selectedFile)}
              className="p-3 bg-gradient-to-r from-cyan-500 via-indigo-600 to-emerald-500 hover:from-cyan-400 hover:to-emerald-400 text-white font-bold rounded-2xl shadow-lg shadow-cyan-500/25 disabled:opacity-30 disabled:cursor-not-allowed transition-all shrink-0"
              title="Send Message"
              aria-label="Send message"
            >
              <svg className="w-5 h-5 transform rotate-90" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            </button>
          </div>
        </div>
      )}

      {/* ── Snapshot Lightbox ─────────────────────────────────────────────── */}
      {previewSnapshot && (
        <div
          className="fixed inset-0 z-[99999] bg-black/85 backdrop-blur-xl flex items-center justify-center p-4"
          onClick={() => setPreviewSnapshot(null)}
          role="dialog"
          aria-label="Snapshot preview"
        >
          <div className="relative max-w-5xl max-h-[90vh] bg-slate-950 rounded-3xl overflow-hidden border border-slate-700/80 shadow-2xl" onClick={(e) => e.stopPropagation()}>
            <img src={previewSnapshot} alt="Full Snapshot Preview" className="max-h-[82vh] w-auto object-contain" />
            <button
              onClick={() => setPreviewSnapshot(null)}
              className="absolute top-4 right-4 p-2.5 bg-slate-900/90 hover:bg-slate-800 text-white font-bold rounded-full border border-slate-700 shadow-xl transition-all"
              aria-label="Close snapshot preview"
            >✕</button>
          </div>
        </div>
      )}
    </>
  );
}