import React, { useState, useEffect } from 'react';

export default function TrajectoryMap({ token }) {
  const [targetId, setTargetId] = useState('MH04AB1234');
  const [loading, setLoading] = useState(false);
  const [trajectoryData, setTrajectoryData] = useState(null);
  const [coOccurrenceData, setCoOccurrenceData] = useState(null);
  const [activeNodeIdx, setActiveNodeIdx] = useState(0);
  const [error, setError] = useState('');

  const fetchTrajectory = (queryId) => {
    if (!token) return;
    setLoading(true);
    setError('');

    fetch(`/api/v1/forensics/trajectory/${encodeURIComponent(queryId || targetId)}`, {
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(res => {
        if (!res.ok) throw new Error("Failed to fetch target trajectory");
        return res.json();
      })
      .then(data => {
        setTrajectoryData(data);
        setActiveNodeIdx(0);
        setLoading(false);
      })
      .catch(err => {
        console.error(err);
        setError(err.message);
        setLoading(false);
      });

    // Also fetch Co-Occurrence groups
    fetch(`/api/v1/forensics/co-occurrence`, {
      headers: { 'Authorization': `Bearer ${token}` }
    })
      .then(res => res.json())
      .then(data => setCoOccurrenceData(data))
      .catch(err => console.error("Co-occurrence error:", err));
  };

  useEffect(() => {
    fetchTrajectory('MH04AB1234');
  }, [token]);

  const handleSearch = (e) => {
    e.preventDefault();
    fetchTrajectory(targetId);
  };

  const nodes = trajectoryData?.trajectory || [];

  return (
    <div style={{ padding: '24px', background: '#0b0f19', color: '#f8fafc', minHeight: '100vh', fontFamily: 'Inter, sans-serif' }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px', borderBottom: '1px solid #1e293b', paddingBottom: '16px' }}>
        <div>
          <h2 style={{ margin: 0, color: '#f8fafc', fontSize: '22px', fontWeight: '700' }}>
            🗺️ Multi-Camera Trajectory & GIS Route Map
          </h2>
          <p style={{ margin: '4px 0 0 0', color: '#94a3b8', fontSize: '13px' }}>
            Chronological suspect movement reconstruction across municipal, traffic & private CCTV nodes
          </p>
        </div>
        <form onSubmit={handleSearch} style={{ display: 'flex', gap: '10px' }}>
          <input
            type="text"
            value={targetId}
            onChange={(e) => setTargetId(e.target.value)}
            placeholder="Enter Plate, POI ID, or Attribute..."
            style={{
              background: '#1e293b',
              border: '1px solid #334155',
              color: '#f8fafc',
              padding: '10px 16px',
              borderRadius: '8px',
              width: '280px',
              outline: 'none',
              fontSize: '14px'
            }}
          />
          <button
            type="submit"
            disabled={loading}
            style={{
              background: 'linear-gradient(135deg, #0284c7 0%, #2563eb 100%)',
              color: 'white',
              border: 'none',
              padding: '10px 20px',
              borderRadius: '8px',
              fontWeight: '600',
              cursor: 'pointer',
              boxShadow: '0 4px 12px rgba(37,99,235,0.3)'
            }}
          >
            {loading ? 'Searching...' : '🔍 Track Route'}
          </button>
        </form>
      </div>

      {error && (
        <div style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid #ef4444', color: '#fca5a5', padding: '12px 16px', borderRadius: '8px', marginBottom: '20px' }}>
          ⚠️ {error}
        </div>
      )}

      {/* Main Grid: Map Visualizer + Sequence Timeline */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 380px', gap: '24px' }}>
        
        {/* Left Column: Interactive GIS Route Map (Surat City Simulation Canvas) */}
        <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '12px', padding: '20px', display: 'flex', flexDirection: 'column' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h3 style={{ margin: 0, fontSize: '15px', color: '#38bdf8' }}>
              Surat City Surveillance Grid Map • Target: <span style={{ color: '#fbbf24' }}>{trajectoryData?.target_id || targetId}</span>
            </h3>
            <span style={{ background: '#1e293b', padding: '4px 10px', borderRadius: '12px', fontSize: '12px', color: '#94a3b8', border: '1px solid #334155' }}>
              {nodes.length} Camera Hits Verified
            </span>
          </div>

          {/* Map Vector Canvas Simulation */}
          <div style={{
            height: '420px',
            background: 'radial-gradient(circle at 50% 50%, #1e293b 0%, #0f172a 100%)',
            border: '1px solid #334155',
            borderRadius: '8px',
            position: 'relative',
            overflow: 'hidden'
          }}>
            {/* Grid Lines */}
            <div style={{
              position: 'absolute', width: '100%', height: '100%',
              backgroundImage: 'linear-gradient(rgba(51,65,85,0.2) 1px, transparent 1px), linear-gradient(90deg, rgba(51,65,85,0.2) 1px, transparent 1px)',
              backgroundSize: '40px 40px'
            }} />

            {/* Polyline Route Connection */}
            <svg style={{ position: 'absolute', width: '100%', height: '100%', top: 0, left: 0, pointerEvents: 'none' }}>
              {nodes.map((node, i) => {
                if (i === 0) return null;
                const prev = nodes[i - 1];
                // Map coords to canvas %
                const x1 = ((prev.longitude - 72.8100) / 0.0400) * 100;
                const y1 = (1.0 - (prev.latitude - 21.1800) / 0.0350) * 100;
                const x2 = ((node.longitude - 72.8100) / 0.0400) * 100;
                const y2 = (1.0 - (node.latitude - 21.1800) / 0.0350) * 100;
                return (
                  <line
                    key={i}
                    x1={`${Math.min(95, Math.max(5, x1))}%`}
                    y1={`${Math.min(95, Math.max(5, y1))}%`}
                    x2={`${Math.min(95, Math.max(5, x2))}%`}
                    y2={`${Math.min(95, Math.max(5, y2))}%`}
                    stroke="#0284c7"
                    strokeWidth="3"
                    strokeDasharray="6 4"
                  />
                );
              })}
            </svg>

            {/* Map Camera Markers */}
            {nodes.map((node, i) => {
              const x = Math.min(92, Math.max(8, ((node.longitude - 72.8100) / 0.0400) * 100));
              const y = Math.min(92, Math.max(8, (1.0 - (node.latitude - 21.1800) / 0.0350) * 100));
              const isActive = i === activeNodeIdx;

              return (
                <div
                  key={i}
                  onClick={() => setActiveNodeIdx(i)}
                  style={{
                    position: 'absolute',
                    left: `${x}%`,
                    top: `${y}%`,
                    transform: 'translate(-50%, -50%)',
                    cursor: 'pointer',
                    zIndex: isActive ? 10 : 2
                  }}
                >
                  <div style={{
                    width: isActive ? '36px' : '28px',
                    height: isActive ? '36px' : '28px',
                    borderRadius: '50%',
                    background: isActive ? 'linear-gradient(135deg, #f59e0b, #ef4444)' : 'linear-gradient(135deg, #0284c7, #2563eb)',
                    border: '2px solid #ffffff',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontWeight: 'bold',
                    fontSize: '12px',
                    color: 'white',
                    boxShadow: isActive ? '0 0 20px rgba(245,158,11,0.8)' : '0 2px 8px rgba(0,0,0,0.5)',
                    transition: 'all 0.3s ease'
                  }}>
                    {i + 1}
                  </div>
                  <div style={{
                    position: 'absolute',
                    top: '32px',
                    left: '50%',
                    transform: 'translateX(-50%)',
                    whiteSpace: 'nowrap',
                    background: '#0f172a',
                    border: '1px solid #334155',
                    padding: '2px 8px',
                    borderRadius: '4px',
                    fontSize: '11px',
                    color: isActive ? '#f59e0b' : '#cbd5e1'
                  }}>
                    {node.camera_name}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Active Node Detail Footer */}
          {nodes[activeNodeIdx] && (
            <div style={{ marginTop: '16px', background: '#1e293b', border: '1px solid #334155', padding: '16px', borderRadius: '8px', display: 'flex', gap: '20px', alignItems: 'center' }}>
              <div style={{
                width: '90px', height: '60px', background: '#0f172a', borderRadius: '6px', border: '1px solid #475569',
                display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#64748b', fontSize: '11px'
              }}>
                📷 Snapshot
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: '15px', fontWeight: 'bold', color: '#38bdf8' }}>
                  Node #{activeNodeIdx + 1}: {nodes[activeNodeIdx].camera_name} ({nodes[activeNodeIdx].location})
                </div>
                <div style={{ fontSize: '13px', color: '#cbd5e1', marginTop: '4px' }}>
                  🕒 Time: <strong>{nodes[activeNodeIdx].timestamp}</strong> • Speed: <strong>{nodes[activeNodeIdx].speed_kmh} km/h</strong> • GIS: {nodes[activeNodeIdx].latitude}, {nodes[activeNodeIdx].longitude}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Right Column: Chronological Hit Sequence & Co-Occurrence Intelligence */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
          
          {/* Hit Sequence List */}
          <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '12px', padding: '16px' }}>
            <h3 style={{ margin: '0 0 12px 0', fontSize: '14px', color: '#f8fafc' }}>
              ⏱️ Chronological Camera Hits
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', maxHeight: '280px', overflowY: 'auto' }}>
              {nodes.map((node, idx) => (
                <div
                  key={idx}
                  onClick={() => setActiveNodeIdx(idx)}
                  style={{
                    padding: '10px 12px',
                    borderRadius: '8px',
                    background: idx === activeNodeIdx ? '#1e293b' : '#0b0f19',
                    border: idx === activeNodeIdx ? '1px solid #0284c7' : '1px solid #1e293b',
                    cursor: 'pointer',
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center'
                  }}
                >
                  <div>
                    <div style={{ fontSize: '13px', fontWeight: 'bold', color: idx === activeNodeIdx ? '#38bdf8' : '#f8fafc' }}>
                      #{idx + 1} {node.camera_name}
                    </div>
                    <div style={{ fontSize: '11px', color: '#94a3b8' }}>
                      {node.timestamp}
                    </div>
                  </div>
                  <span style={{ fontSize: '11px', background: '#0f172a', padding: '2px 8px', borderRadius: '4px', border: '1px solid #334155', color: '#fbbf24' }}>
                    {node.speed_kmh} km/h
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Co-Occurrence Accomplice Grouping Intelligence (Use Case 23) */}
          <div style={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: '12px', padding: '16px' }}>
            <h3 style={{ margin: '0 0 8px 0', fontSize: '14px', color: '#a855f7' }}>
              🤝 Spatial-Temporal Co-Occurrence Linking (Use Case 23)
            </h3>
            <p style={{ margin: '0 0 12px 0', fontSize: '12px', color: '#94a3b8' }}>
              Identified candidate suspect accomplices in same time-spatial window:
            </p>
            {coOccurrenceData?.co_occurrence_groups?.map((grp, idx) => (
              <div key={idx} style={{ background: '#18181b', border: '1px solid #27272a', padding: '12px', borderRadius: '8px' }}>
                <div style={{ fontSize: '12px', fontWeight: 'bold', color: '#c084fc', marginBottom: '6px' }}>
                  {grp.group_id} • Confidence: {grp.confidence_score * 100}%
                </div>
                <div style={{ fontSize: '11px', color: '#a1a1aa' }}>
                  {grp.analytical_summary}
                </div>
              </div>
            ))}
          </div>

        </div>

      </div>
    </div>
  );
}
