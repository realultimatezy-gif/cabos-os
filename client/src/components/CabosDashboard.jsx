import React, { useState, useEffect } from 'react';

export default function CabosDashboard() {
  const [botStatus, setBotStatus] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Fetch live status from backend driver route
    fetch('/api/bots/status') // Or your full backend URL if hosted separately
      .then(res => res.json())
      .then(data => {
        setBotStatus(data);
        setLoading(false);
      })
      .catch(err => {
        console.error('Error fetching bot status:', err);
        setLoading(false);
      });
  }, []);

  return (
    <div className="p-6 bg-slate-900 text-white min-h-screen font-sans">
      <header className="mb-8 border-b border-slate-700 pb-4">
        <h1 className="text-3xl font-bold tracking-wider text-emerald-400">CABOS SOVEREIGN OS</h1>
        <p className="text-sm text-slate-400">Autonomous Robotics & Offline-First Intelligence Dashboard</p>
      </header>

      {loading ? (
        <div className="text-emerald-500 animate-pulse">Scanning CABOS node drivers...</div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Jack - Ground Patrol Driver */}
          <div className="bg-slate-800 p-5 rounded-xl border border-slate-700 shadow-lg">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-xl font-semibold text-amber-400">🐕 Jack (Dog Bot)</h2>
              <span className="px-3 py-1 bg-emerald-900 text-emerald-300 text-xs rounded-full">Active Driver</span>
            </div>
            <p className="text-sm text-slate-300 mb-2"><strong>Role:</strong> Ground Patrol & Gate Security</p>
            <p className="text-sm text-slate-300 mb-4"><strong>Zone:</strong> Yard, Gate & Street</p>
            <div className="bg-slate-900 p-3 rounded text-xs font-mono text-emerald-400">
              Status: Patrol Ground Obstacles [OK]
            </div>
          </div>

          {/* Dodo - Aerial Drone Driver */}
          <div className="bg-slate-800 p-5 rounded-xl border border-slate-700 shadow-lg">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-xl font-semibold text-cyan-400">🐈 Dodo (Cat Bot)</h2>
              <span className="px-3 py-1 bg-emerald-900 text-emerald-300 text-xs rounded-full">Active Driver</span>
            </div>
            <p className="text-sm text-slate-300 mb-2"><strong>Role:</strong> Aerial Drone & Vault Hunter</p>
            <p className="text-sm text-slate-300 mb-4"><strong>Zone:</strong> Reading Room, Trees & Sky</p>
            <div className="bg-slate-900 p-3 rounded text-xs font-mono text-cyan-400">
              Status: Stealth Flight Mapping [READY]
            </div>
          </div>
        </div>
      )}

      {/* System Engine Footer */}
      <div className="mt-8 bg-slate-800 p-4 rounded-lg border border-slate-700 flex justify-between items-center text-sm">
        <span className="text-slate-400">Offline Fallback Engine: <span className="text-emerald-400">Enabled</span></span>
        <span className="text-slate-400">Google Drive Sync: <span className="text-amber-400">Standby</span></span>
      </div>
    </div>
  );
}
