import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import './AIChatbot.css';

// ---- Config -----------------------------------------------------------------

const SESSION_STORAGE_KEY = 'vms_chat_session_id';
const MAX_IMAGE_BYTES = 15 * 1024 * 1024;
const ALLOWED_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/webp'];
const NEAR_BOTTOM_THRESHOLD_PX = 120;
const AI_NAME = 'Sybau Forensic AI';

// ---- Search Mode Definitions ----
const SEARCH_MODES = [
  { id: 'all', label: 'All / Auto', icon: '🌐', desc: 'Scan faces, vehicles, plates & text' },
  { id: 'face', label: 'Face Match', icon: '👤', desc: 'Biometric facial recognition search' },
  { id: 'plate', label: 'Number Plate', icon: '🚗', desc: 'Strict ALPR license plate search' },
  { id: 'ocr', label: 'OCR Text', icon: '🔤', desc: 'On-screen signage & text search' },
];

// ---- Dynamic Greeting Helper ----
function getDynamicGreeting() {
  const hour = new Date().getHours();
  let timeStr = 'Good Day';
  if (hour >= 5 && hour < 12) timeStr = 'Good Morning';
  else if (hour >= 12 && hour < 17) timeStr = 'Good Afternoon';
  else if (hour >= 17 && hour < 22) timeStr = 'Good Evening';
  else timeStr = 'Night Surveillance Ops';
  return `${timeStr}, Officer! 👋`;
}

// ---- Inline Markdown Renderer ----
function renderInline(text, keyPrefix) {
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g).filter(Boolean);
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={`${keyPrefix}-${i}`} style={{ color: '#38bdf8', fontWeight: 700 }}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith('*') && part.endsWith('*')) {
      return <em key={`${keyPrefix}-${i}`} style={{ color: '#94a3b8', fontStyle: 'italic' }}>{part.slice(1, -1)}</em>;
    }
    return <React.Fragment key={`${keyPrefix}-${i}`}>{part}</React.Fragment>;
  });
}

function MessageText({ text }) {
  return (
    <div style={{ whiteSpace: 'pre-wrap', lineHeight: 1.55 }}>
      {text.split('\n').map((line, idx) => (
        <p key={idx} style={{ marginTop: idx > 0 ? '6px' : '0', marginBottom: '0' }}>
          {line ? renderInline(line, idx) : '\u00A0'}
        </p>
      ))}
    </div>
  );
}

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

// ---- Draggable Hook ---------------------------------------------------------
function useDraggable(initialPos) {
  const [pos, setPos] = useState(initialPos);
  const [isDraggingState, setIsDraggingState] = useState(false);
  const isDragging = useRef(false);
  const startOffset = useRef({ x: 0, y: 0 });

  const onMouseDown = useCallback((e) => {
    if (e.target.closest('button') || e.target.closest('input') || e.target.closest('.ai-chat-sidebar')) return;
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
      const newX = Math.max(10, Math.min(windowWidth - 520, e.clientX - startOffset.current.x));
      const newY = Math.max(10, Math.min(windowHeight - 100, e.clientY - startOffset.current.y));
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

  return { pos, setPos, onMouseDown, isDragging: isDraggingState };
}

// ---- Main Component ----------------------------------------------------------

export default function AIChatbot({ token: propToken }) {
  const token = propToken || (typeof window !== 'undefined' ? localStorage.getItem('token') : null);
  const [isOpen, setIsOpen] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);
  const [sessionId, setSessionId] = useState(loadOrCreateSessionId);
  const [searchMode, setSearchMode] = useState('all');
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [sessionsList, setSessionsList] = useState([]);
  const [messages, setMessages] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [inputQuery, setInputQuery] = useState('');
  const [selectedFile, setSelectedFile] = useState(null);
  const [imagePreview, setImagePreview] = useState(null);
  const [imageError, setImageError] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [unreadCount, setUnreadCount] = useState(0);
  const [suggestions, setSuggestions] = useState([
    'Koi blue shirt wala banda station pr dikha kya?',
    'Laal color ki car spot hui kya gate ke paas?',
    'Bina helmet motorcycle chalane wala koi mila?',
    'Show me suspicious crowd activity near bus depo'
  ]);
  const [previewSnapshot, setPreviewSnapshot] = useState(null);
  const [lastFailedPayload, setLastFailedPayload] = useState(null);

  const messagesEndRef = useRef(null);
  const scrollContainerRef = useRef(null);
  const fileInputRef = useRef(null);
  const inputRef = useRef(null);
  const abortControllerRef = useRef(null);
  const stickToBottomRef = useRef(true);

  const defaultPos = useMemo(() => ({
    x: Math.max(20, window.innerWidth - 560),
    y: Math.max(20, window.innerHeight - 700)
  }), []);

  const { pos, onMouseDown, isDragging } = useDraggable(defaultPos);

  const authUrl = useCallback((url) => {
    if (!url) return '';
    if (url.startsWith('data:') || url.startsWith('blob:')) return url;
    const activeToken = token || (typeof window !== 'undefined' ? localStorage.getItem('token') : null);
    if (activeToken && !url.includes('token=')) {
      return url.includes('?') ? `${url}&token=${encodeURIComponent(activeToken)}` : `${url}?token=${encodeURIComponent(activeToken)}`;
    }
    return url;
  }, [token]);

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

  // Fetch Suggestions
  useEffect(() => {
    const headers = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    fetch('/api/v1/chat/suggestions', { headers })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => { if (data?.suggestions?.length) setSuggestions(data.suggestions); })
      .catch(() => { });
  }, [token]);

  // Fetch Sessions List
  const refreshSessions = useCallback(() => {
    const headers = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    fetch('/api/v1/chat/sessions', { headers })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data?.sessions) setSessionsList(data.sessions);
      })
      .catch(() => { });
  }, [token]);

  useEffect(() => {
    if (isOpen) {
      refreshSessions();
    }
  }, [isOpen, refreshSessions]);

  // Fetch History for Active Session
  const loadHistoryForSession = useCallback((targetSessionId) => {
    setHistoryLoading(true);
    const headers = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    fetch(`/api/v1/chat/history?session_id=${encodeURIComponent(targetSessionId)}&limit=50`, { headers })
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
        } else {
          setMessages([]);
        }
      })
      .catch(() => { setMessages([]); })
      .finally(() => setHistoryLoading(false));
  }, [token]);

  useEffect(() => {
    if (isOpen) {
      loadHistoryForSession(sessionId);
    }
  }, [isOpen, sessionId, loadHistoryForSession]);

  useEffect(() => { return () => abortControllerRef.current?.abort(); }, []);

  // Create New Clean Investigation Session
  const handleNewSession = () => {
    abortControllerRef.current?.abort();
    const freshId = `chat_${Date.now().toString(36)}_${Math.random().toString(36).substring(2, 6)}`;
    try { window.localStorage.setItem(SESSION_STORAGE_KEY, freshId); } catch { /* ignore */ }
    setSessionId(freshId);
    setMessages([]);
    setInputQuery('');
    clearSelectedFile();
    setIsLoading(false);
    setIsSidebarOpen(false);
    setTimeout(() => inputRef.current?.focus(), 50);
  };

  // Switch Session
  const handleSelectSession = (sId) => {
    if (sId === sessionId) return;
    try { window.localStorage.setItem(SESSION_STORAGE_KEY, sId); } catch { /* ignore */ }
    setSessionId(sId);
    clearSelectedFile();
    setIsSidebarOpen(false);
  };

  // Delete Session
  const handleDeleteSession = async (e, sId) => {
    e.stopPropagation();
    const headers = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    try {
      await fetch(`/api/v1/chat/session/${encodeURIComponent(sId)}`, { method: 'DELETE', headers });
      refreshSessions();
      if (sId === sessionId) {
        handleNewSession();
      }
    } catch { }
  };

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setImageError(null);
    if (!ALLOWED_IMAGE_TYPES.includes(file.type)) {
      setImageError('Unsupported format — use JPG, PNG, or WEBP.');
      e.target.value = '';
      return;
    }
    if (file.size > MAX_IMAGE_BYTES) {
      setImageError(`Image too large (max ${Math.round(MAX_IMAGE_BYTES / (1024 * 1024))}MB).`);
      e.target.value = '';
      return;
    }
    setSelectedFile(file);
    const reader = new FileReader();
    reader.onloadend = () => setImagePreview(reader.result);
    reader.onerror = () => setImageError('Could not read file.');
    reader.readAsDataURL(file);
  };

  const clearSelectedFile = () => {
    setSelectedFile(null);
    setImagePreview(null);
    setImageError(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

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

    const authHeaders = token ? { 'Authorization': `Bearer ${token}` } : {};

    try {
      let resp;
      if (fileToSend) {
        const formData = new FormData();
        formData.append('file', fileToSend);
        if (textToSend) formData.append('query', textToSend);
        formData.append('session_id', sessionId);
        formData.append('mode', searchMode);
        resp = await fetch('/api/v1/chat/upload-search', {
          method: 'POST',
          headers: { ...authHeaders },
          body: formData,
          signal: controller.signal
        });
      } else {
        resp = await fetch('/api/v1/chat/message', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...authHeaders },
          body: JSON.stringify({ query: textToSend, session_id: sessionId, mode: searchMode }),
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
      refreshSessions();
      if (!isOpen) setUnreadCount((c) => c + 1);
    } catch (err) {
      if (err.name === 'AbortError') return;
      setLastFailedPayload({ text: textToSend, file: fileToSend });
      setMessages((prev) => [
        ...prev,
        {
          id: `err_${Date.now()}`,
          sender: 'assistant',
          text: '⚠️ An error occurred while communicating with Sybau AI. Check server connectivity.',
          isError: true,
          timestamp: nowLabel(),
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const activeModeInfo = SEARCH_MODES.find((m) => m.id === searchMode) || SEARCH_MODES[0];

  return (
    <>
      {/* Lightbox / Snapshot Zoom Modal */}
      {previewSnapshot && (
        <div className="ai-chat-lightbox-backdrop" onClick={() => setPreviewSnapshot(null)}>
          <div className="ai-chat-lightbox-content" onClick={(e) => e.stopPropagation()}>
            <img src={previewSnapshot} alt="Forensic Snapshot" className="ai-chat-lightbox-img" />
            <button className="ai-chat-lightbox-close" onClick={() => setPreviewSnapshot(null)}>✕</button>
          </div>
        </div>
      )}

      {/* Floating Tactical Launcher Badge */}
      {!isOpen && (
        <div
          className="ai-chat-launcher"
          onClick={() => setIsOpen(true)}
          role="button"
          tabIndex={0}
          aria-label="Open Sybau AI Copilot"
        >
          <div className="ai-chat-launcher-icon">
            <svg width="20" height="20" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <div className="ai-chat-launcher-info">
            <div className="ai-chat-launcher-title">
              SYBAU FORENSIC AI
              <span className="ai-chat-tag-live">ONLINE</span>
            </div>
            <div className="ai-chat-launcher-sub">Multi-Modal Face & ALPR Copilot</div>
          </div>
          {unreadCount > 0 && <span className="ai-chat-badge">{unreadCount}</span>}
        </div>
      )}

      {/* Main Forensic AI Copilot Window */}
      {isOpen && (
        <div
          className={`ai-chat-modal ${isExpanded ? 'ai-chat-modal-expanded' : ''}`}
          style={isExpanded ? {} : { left: `${pos.x}px`, top: `${pos.y}px` }}
        >
          {/* Header Bar */}
          <div className="ai-chat-header" onMouseDown={isExpanded ? undefined : onMouseDown}>
            <div className="ai-chat-header-brand">
              <button
                className={`ai-chat-sidebar-toggle-btn ${isSidebarOpen ? 'active' : ''}`}
                onClick={() => setIsSidebarOpen(!isSidebarOpen)}
                title="Investigation History"
              >
                <svg width="18" height="18" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6h16M4 12h16M4 18h7" />
                </svg>
              </button>

              <div className="ai-chat-avatar">
                <div className="ai-chat-avatar-inner">
                  <svg width="18" height="18" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                </div>
              </div>
              <div>
                <div className="ai-chat-header-title">
                  {AI_NAME}
                  <span className="ai-chat-status-dot" />
                </div>
                <div className="ai-chat-header-subtitle">
                  {activeModeInfo.icon} {activeModeInfo.label} Active • Session: <span style={{ fontFamily: 'monospace', color: '#38bdf8' }}>{sessionId.slice(0, 10)}</span>
                </div>
              </div>
            </div>

            <div className="ai-chat-header-actions">
              <button
                className="ai-chat-action-btn ai-chat-btn-new-glow"
                onClick={handleNewSession}
                title="Start New Investigation Chat"
              >
                ➕ New
              </button>
              <button
                className="ai-chat-action-btn"
                onClick={() => setIsExpanded(!isExpanded)}
                title={isExpanded ? 'Restore Window' : 'Expand Fullscreen'}
              >
                {isExpanded ? '🗗' : '⛶'}
              </button>
              <button
                className="ai-chat-action-btn ai-chat-close-btn"
                onClick={() => setIsOpen(false)}
                title="Close"
              >
                ✕
              </button>
            </div>
          </div>

          {/* Main Body with Split Sidebar */}
          <div className="ai-chat-body-container">
            {/* Sidebar (History & Session Switcher) */}
            {isSidebarOpen && (
              <div className="ai-chat-sidebar">
                <div className="ai-chat-sidebar-header">
                  <span>📁 INVESTIGATIONS</span>
                  <button className="ai-chat-new-chat-btn" onClick={handleNewSession}>
                    ➕ New Chat
                  </button>
                </div>
                <div className="ai-chat-sessions-list">
                  {sessionsList.length === 0 ? (
                    <div className="ai-chat-sessions-empty">No prior investigations saved.</div>
                  ) : (
                    sessionsList.map((s) => (
                      <div
                        key={s.session_uuid}
                        className={`ai-chat-session-item ${s.session_uuid === sessionId ? 'active' : ''}`}
                        onClick={() => handleSelectSession(s.session_uuid)}
                      >
                        <div className="ai-chat-session-title" title={s.title}>{s.title}</div>
                        <div className="ai-chat-session-meta">
                          <span>💬 {s.message_count}</span>
                          <button
                            className="ai-chat-session-del-btn"
                            onClick={(e) => handleDeleteSession(e, s.session_uuid)}
                            title="Delete Session"
                          >
                            🗑️
                          </button>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}

            {/* Chat Messages Stream */}
            <div className="ai-chat-stream" ref={scrollContainerRef} onScroll={handleScroll}>
              {messages.length === 0 && !historyLoading && (
                <div className="ai-chat-empty-welcome">
                  <div className="ai-chat-welcome-icon">🛡️</div>
                  <div className="ai-chat-welcome-title">{getDynamicGreeting()}</div>
                  <div className="ai-chat-welcome-desc">
                    I am your AI Surveillance Copilot. You can ask queries, upload target photos for biometric face recognition, verify license plates, or search across city camera streams.
                  </div>

                  {/* Suggestion Chips */}
                  <div className="ai-chat-suggestions-grid">
                    {suggestions.map((s, idx) => (
                      <button
                        key={idx}
                        className="ai-chat-suggestion-chip"
                        onClick={() => handleSend(s)}
                      >
                        <span>🔎</span> {s}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {historyLoading && (
                <div className="ai-chat-loading-history">
                  <span className="ai-chat-spinner" /> Loading investigation history…
                </div>
              )}

              {messages.map((msg) => (
                <div
                  key={msg.id}
                  className={`ai-chat-msg-row ${msg.sender === 'user' ? 'ai-chat-msg-user' : 'ai-chat-msg-bot'}`}
                >
                  <div className="ai-chat-msg-bubble">
                    {/* Attached Photo */}
                    {msg.image_url && (
                      <div className="ai-chat-msg-image-wrap">
                        <img
                          src={authUrl(msg.image_url)}
                          alt="Attached Visual Target"
                          className="ai-chat-msg-thumb"
                          onClick={() => setPreviewSnapshot(authUrl(msg.image_url))}
                        />
                        <span className="ai-chat-msg-image-tag">Target Reference</span>
                      </div>
                    )}

                    <MessageText text={msg.text} />

                    {/* Timeline & Evidence Cards */}
                    {msg.timeline && msg.timeline.length > 0 && (
                      <div className="ai-chat-evidence-container">
                        <div className="ai-chat-evidence-header">
                          <span>🚨 VERIFIED EVIDENCE TRAIL ({msg.timeline.length})</span>
                        </div>
                        <div className="ai-chat-evidence-grid">
                          {msg.timeline.map((item, iIdx) => (
                            <div key={iIdx} className="ai-chat-evidence-card">
                              {item.snapshot_url ? (
                                <img
                                  src={authUrl(item.snapshot_url)}
                                  alt="Sighting Snapshot"
                                  className="ai-chat-evidence-thumb"
                                  onClick={() => setPreviewSnapshot(authUrl(item.snapshot_url))}
                                  onError={(e) => {
                                    e.target.onerror = null;
                                    e.target.src = authUrl(`/api/v1/playback/snapshot/cam_${item.camera_id}`);
                                  }}
                                />
                              ) : (
                                <div className="ai-chat-evidence-no-pic">📷 SNAPSHOT</div>
                              )}
                              <div className="ai-chat-evidence-details">
                                <div className="ai-chat-evidence-cam">{item.camera_name}</div>
                                <div className="ai-chat-evidence-time">⏱️ {item.time_display}</div>
                                <div className="ai-chat-evidence-desc">{item.description}</div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}

                    {/* Trajectory */}
                    {msg.trajectory && msg.trajectory.legs && msg.trajectory.legs.length > 0 && (
                      <div className="ai-chat-trajectory-wrap">
                        <div className="ai-chat-trajectory-title">🗺️ INFERRED TRAJECTORY PATH</div>
                        {msg.trajectory.legs.map((leg, lIdx) => (
                          <div key={lIdx} className="ai-chat-trajectory-leg">
                            <strong>{leg.from_camera}</strong>
                            <span>➔</span>
                            <strong>{leg.to_camera}</strong>
                            {leg.gap_minutes != null && <span className="ai-chat-gap">({leg.gap_minutes}m gap)</span>}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                  <span className="ai-chat-msg-time">{msg.timestamp}</span>
                </div>
              ))}

              {isLoading && (
                <div className="ai-chat-loading-indicator">
                  <span className="ai-chat-radar-spinner" />
                  <span>Scanning multi-camera neural memory & biometrics…</span>
                </div>
              )}
              <div ref={messagesEndRef} />
            </div>
          </div>

          {/* Search Mode Filter Bar */}
          <div className="ai-chat-mode-bar">
            <span className="ai-chat-mode-label">FILTER:</span>
            {SEARCH_MODES.map((m) => (
              <button
                key={m.id}
                className={`ai-chat-mode-btn ${searchMode === m.id ? 'active' : ''}`}
                onClick={() => setSearchMode(m.id)}
                title={m.desc}
              >
                <span>{m.icon}</span> {m.label}
              </button>
            ))}
          </div>

          {/* Image Attachment Preview */}
          {(imagePreview || imageError) && (
            <div className="ai-chat-preview-bar">
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                {imagePreview && (
                  <img src={imagePreview} alt="Attached Target" className="ai-chat-preview-thumb" />
                )}
                <div>
                  {imageError ? (
                    <div style={{ color: '#f87171', fontSize: '11px', fontWeight: 700 }}>{imageError}</div>
                  ) : (
                    <>
                      <div style={{ color: '#f8fafc', fontSize: '11px', fontWeight: 700 }}>Target Image Attached</div>
                      <div style={{ color: '#38bdf8', fontSize: '10px' }}>
                        {searchMode === 'face' ? '👤 Biometric Face Search Enabled' : 'Vision Target Scan Active'}
                      </div>
                    </>
                  )}
                </div>
              </div>
              <button onClick={clearSelectedFile} className="ai-chat-preview-clear-btn">✕</button>
            </div>
          )}

          {/* Input Form Bar */}
          <div className="ai-chat-input-bar">
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              accept="image/jpeg,image/png,image/webp"
              className="ai-chat-file-input"
            />

            <button
              onClick={() => fileInputRef.current?.click()}
              className="ai-chat-attach-btn"
              title="Upload image to match face/vehicle/scene"
              aria-label="Upload image"
            >
              <svg width="18" height="18" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
              </svg>
            </button>

            <input
              ref={inputRef}
              type="text"
              value={inputQuery}
              onChange={(e) => setInputQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                searchMode === 'face'
                  ? 'Search person face or upload portrait…'
                  : searchMode === 'plate'
                  ? 'Enter number plate (e.g. GJ05AB1234)…'
                  : searchMode === 'ocr'
                  ? 'Search text overlay or signage…'
                  : `Ask ${AI_NAME} anything… (English / Hinglish)`
              }
              aria-label="Message Query"
              className="ai-chat-text-input"
            />

            <button
              onClick={() => handleSend()}
              disabled={isLoading || (!inputQuery.trim() && !selectedFile)}
              className="ai-chat-send-btn"
              title="Send Message"
              aria-label="Send message"
            >
              <svg width="18" height="18" style={{ transform: 'rotate(90deg)' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.2" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
            </button>
          </div>
        </div>
      )}
    </>
  );
}