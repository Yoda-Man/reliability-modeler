'use client';

import React, { useState } from 'react';
import { ShieldCheck, Database, LayoutDashboard, Settings, Info, Menu, X, Book, Shield, Heart } from 'lucide-react';
import FileUpload from '@/components/FileUpload';
import Dashboard from '@/components/Dashboard';
import MethodologyView from '@/components/Methodology';
import ConfigView from '@/components/ConfigView';
import LogsView from '@/components/LogsView';
import UserManualView from '@/components/UserManualView';
import PrivacyPolicy from '@/components/PrivacyPolicy';
import AboutView from '@/components/AboutView';

export default function Home() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [results, setResults] = useState<any>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(false);
  const [futureHours, setFutureHours] = useState(1000);

  const handleFileUpload = async (file: File) => {
    setIsAnalyzing(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/analyze?future_hours=${futureHours}`, {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) throw new Error('Analysis failed');

      const data = await response.json();
      setResults(data);
    } catch (error) {
      console.error('Error analyzing file:', error);
      alert('Failed to analyze the file. Please ensure it follows the expected format.');
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleSampleData = async () => {
    setIsAnalyzing(true);
    try {
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/sample-data`);
      if (!response.ok) throw new Error('Sample data analysis failed');
      const data = await response.json();
      setResults(data);
      setActiveTab('dashboard');
    } catch (error) {
      console.error('Error fetching sample data:', error);
      alert('Failed to load sample data.');
    } finally {
      setIsAnalyzing(false);
    }
  };

  const renderContent = () => {
    if (activeTab === 'methodology') return <MethodologyView />;
    if (activeTab === 'logs') return <LogsView />;
    if (activeTab === 'config') return <ConfigView />;
    if (activeTab === 'user-manual') return <UserManualView />;
    if (activeTab === 'privacy') return <PrivacyPolicy />;
    if (activeTab === 'about') return <AboutView />;

    // Dashboard View
    if (!results) {
      return (
        <div className="space-y-12 animate-in fade-in duration-500">
          <div className="max-w-2xl">
            <h2 className="text-4xl font-extrabold text-white mb-4 tracking-tight leading-tight">
              Software Reliability <br />
              <span className="text-blue-500">Growth Modeler</span>
            </h2>
            <p className="text-lg text-slate-400 leading-relaxed">
              Transform raw error logs into actionable intelligence. Our engine applies advanced
              statistical models to predict system stability and optimize release cycles.
            </p>
          </div>

          <FileUpload
            onFileUpload={handleFileUpload}
            onSampleData={handleSampleData}
            isLoading={isAnalyzing}
          />

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 mt-12">
            <FeatureCard
              title="Predictive Excellence"
              description="Leverage Goel-Okumoto and Musa-Okumoto models to peak into future system reliability."
            />
            <FeatureCard
              title="Categorical Insight"
              description="Automatically group failures and identify root causes with custom taxonomy analysis."
            />
            <FeatureCard
              title="Executive Decisioning"
              description="Data-driven metrics designed for management, providing clear go/no-go indicators."
            />
          </div>
        </div>
      );
    }
    return (
      <div className="print:p-0">
        <Dashboard
          data={results}
          futureHours={futureHours}
          onFutureHoursChange={setFutureHours}
        />
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-[#020617] text-slate-200 selection:bg-blue-500/30">
      {/* Mobile Menu Toggle */}
      <div className="lg:hidden fixed top-4 right-4 z-50">
        <button
          onClick={() => setIsSidebarOpen(!isSidebarOpen)}
          className="p-2 rounded-lg bg-slate-900 border border-slate-800 text-slate-400"
        >
          {isSidebarOpen ? <X /> : <Menu />}
        </button>
      </div>

      {/* Sidebar Overlay */}
      {isSidebarOpen && (
        <div
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40 lg:hidden"
          onClick={() => setIsSidebarOpen(false)}
        />
      )}

      {/* Sidebar */}
      <aside className={`
        fixed left-0 top-0 bottom-0 w-64 bg-slate-950 border-r border-slate-900 z-50
        transition-transform duration-300 flex flex-col
        ${isSidebarOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
      `}>
        <div className="p-6 flex items-center space-x-3 mb-8">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-600 to-emerald-500 flex items-center justify-center shadow-lg shadow-blue-500/20">
            <ShieldCheck className="text-white w-6 h-6" />
          </div>
          <span className="text-xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-400 tracking-tight">
            Reliability
          </span>
        </div>

        <nav className="flex-1 px-4 space-y-2">
          <NavItem
            icon={<LayoutDashboard size={18} />}
            label="Dashboard"
            active={activeTab === 'dashboard'}
            onClick={() => { setActiveTab('dashboard'); setIsSidebarOpen(false); }}
          />
          <NavItem
            icon={<Database size={18} />}
            label="Logs Archive"
            active={activeTab === 'logs'}
            onClick={() => { setActiveTab('logs'); setIsSidebarOpen(false); }}
          />
          <NavItem
            icon={<Settings size={18} />}
            label="Configurations"
            active={activeTab === 'config'}
            onClick={() => { setActiveTab('config'); setIsSidebarOpen(false); }}
          />
          <NavItem
            icon={<Info size={18} />}
            label="Methodology"
            active={activeTab === 'methodology'}
            onClick={() => { setActiveTab('methodology'); setIsSidebarOpen(false); }}
          />
          <div className="pt-4 mt-4 border-t border-slate-900/50">
            <p className="px-4 text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-2">Support & Legal</p>
            <NavItem
              icon={<Book size={18} />}
              label="User Manual"
              active={activeTab === 'user-manual'}
              onClick={() => { setActiveTab('user-manual'); setIsSidebarOpen(false); }}
            />
            <NavItem
              icon={<Shield size={18} />}
              label="Privacy Policy"
              active={activeTab === 'privacy'}
              onClick={() => { setActiveTab('privacy'); setIsSidebarOpen(false); }}
            />
            <NavItem
              icon={<Heart size={18} />}
              label="About Project"
              active={activeTab === 'about'}
              onClick={() => { setActiveTab('about'); setIsSidebarOpen(false); }}
            />
          </div>
        </nav>

        <div className="p-6 border-t border-slate-900">
          <div className="p-4 rounded-xl bg-slate-900/50 border border-slate-800">
            <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-2 font-bold">System Status</p>
            <div className="flex items-center space-x-2">
              <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              <span className="text-xs text-slate-300 font-medium tracking-wide">Operational</span>
            </div>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="lg:pl-64 min-h-screen transition-all duration-300">
        {/* Header */}
        <header className="h-16 border-b border-slate-900 bg-slate-950/50 backdrop-blur-md sticky top-0 z-30 px-8 flex items-center justify-between">
          <div>
            <h1 className="text-sm font-semibold text-slate-300 capitalize">{activeTab} & Analytics</h1>
          </div>
          <div className="flex items-center space-x-4">
            {results && activeTab === 'dashboard' && (
              <button
                onClick={() => { setResults(null); }}
                className="text-xs font-semibold px-4 py-2 rounded-lg bg-slate-800 border border-slate-700 text-slate-300 hover:text-white transition-all"
              >
                Start New Session
              </button>
            )}
            <div className="w-8 h-8 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-xs font-bold text-blue-400">
              TM
            </div>
          </div>
        </header>

        <div className="p-8 max-w-7xl mx-auto">
          {renderContent()}
        </div>
      </main>
    </div>
  );
}

function NavItem({ icon, label, active = false, onClick }: { icon: React.ReactNode; label: string; active?: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`
        w-full flex items-center space-x-3 px-4 py-3 rounded-xl transition-all group
        ${active
          ? 'bg-blue-600/10 text-white border border-blue-500/20'
          : 'text-slate-400 hover:bg-slate-900 hover:text-slate-200'}
      `}
    >
      <span className={active ? 'text-blue-500' : 'group-hover:text-blue-400 transition-colors'}>
        {icon}
      </span>
      <span className="text-sm font-medium">{label}</span>
    </button>
  );

}

function FeatureCard({ title, description }: { title: string; description: string }) {
  return (
    <div className="p-6 rounded-2xl bg-slate-900/30 border border-slate-800/50 hover:border-slate-700 transition-all">
      <h3 className="text-white font-semibold mb-2">{title}</h3>
      <p className="text-sm text-slate-500 leading-relaxed">{description}</p>
    </div>
  );
}
