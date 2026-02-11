import React, { useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import ToolCard from './components/ToolCard';
import RequestInput from './components/RequestInput';
import VideoGenerator from './components/VideoGeneratorBackend';
// import VideoGeneratorVEO from './components/VideoGeneratorVEO';
import AuthModal from './components/AuthModal';
import UserProfile from './components/UserProfile';
import LoadingSpinner from './components/LoadingSpinner';
import LanguageSwitcher from './components/LanguageSwitcher';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { useTools } from './hooks/useTools';
import { Tool } from './types';

const BackgroundNodes = () => (
  <svg
    className="absolute inset-0 w-full h-full z-0 opacity-20"
    xmlns="http://www.w3.org/2000/svg"
    preserveAspectRatio="xMidYMid slice"
  >
    <defs>
      <radialGradient id="grad1" cx="50%" cy="50%" r="50%" fx="50%" fy="50%">
        <stop offset="0%" style={{ stopColor: 'rgb(128,0,128)', stopOpacity: 0.5 }} />
        <stop offset="100%" style={{ stopColor: 'rgb(128,0,128)', stopOpacity: 0 }} />
      </radialGradient>
    </defs>
    <rect width="100%" height="100%" fill="transparent" />
    <g stroke="rgba(192, 132, 252, 0.4)" strokeWidth="1">
      <circle cx="10%" cy="20%" r="2" fill="url(#grad1)" />
      <circle cx="80%" cy="10%" r="3" fill="url(#grad1)" />
      <circle cx="50%" cy="80%" r="4" fill="url(#grad1)" />
      <circle cx="90%" cy="60%" r="2" fill="url(#grad1)" />
      <circle cx="30%" cy="90%" r="3" fill="url(#grad1)" />
      <circle cx="5%" cy="70%" r="2" fill="url(#grad1)" />
      <line x1="10%" y1="20%" x2="80%" y2="10%" />
      <line x1="80%" y1="10%" x2="50%" y2="80%" />
      <line x1="50%" y1="80%" x2="90%" y2="60%" />
      <line x1="90%" y1="60%" x2="30%" y2="90%" />
      <line x1="30%" y1="90%" x2="5%" y2="70%" />
      <line x1="5%" y1="70%" x2="10%" y2="20%" />
    </g>
  </svg>
);

type Page =
  | 'home'
  | 'information'
  | 'news'
  | 'instruction'
  | 'payment'
  | 'generator'
  | 'veo-test';

const AppContent: React.FC = () => {
  console.log('AppContent rendering...');

  const { isAuthenticated, isLoading } = useAuth();
  const { t } = useTranslation();
  const tools = useTools();

  const [activeTool, setActiveTool] = useState<Tool | null>(null);
  const [page, setPage] = useState<Page>('home');
  const [prompt, setPrompt] = useState('');
  const [audioUrl, setAudioUrl] = useState<string | null>(null);
  const [showAuthModal, setShowAuthModal] = useState(false);

  console.log('AppContent state:', { isLoading, isAuthenticated, page, tools: tools?.length });

  const handleCardClick = useCallback((tool: Tool) => {
    setActiveTool(tool);
    setPage('generator');
  }, []);

  const handleBackToHome = useCallback(() => {
    setPage('home');
    setActiveTool(null);
  }, []);

  const handleAuthRequired = useCallback(() => {
    setShowAuthModal(true);
  }, []);

  const menuItems: Array<{ key: Page; label: string }> = [
    { key: 'home', label: 'Home' },
    { key: 'information', label: 'Information' },
    { key: 'news', label: 'News' },
    { key: 'instruction', label: 'Instruction' },
    { key: 'payment', label: 'Payment' },
  ];

  if (isLoading) {
    return (
      <div className="relative min-h-screen w-full bg-gradient-to-br from-[#0a0328] via-[#1a0c4d] to-[#4c1d95] text-white overflow-hidden">
        <BackgroundNodes />
        <main className="relative z-10 flex flex-col items-center justify-center min-h-screen p-4 sm:p-8">
          <LoadingSpinner size="lg" text={t('loading.default')} />
        </main>
      </div>
    );
  }

  return (
    <div className="relative min-h-screen w-full bg-gradient-to-br from-[#0a0328] via-[#1a0c4d] to-[#4c1d95] text-white overflow-hidden">
      <BackgroundNodes />

      {/* Top Navigation */}
      <nav className="relative z-20 flex justify-between items-center p-6">
        <div className="flex items-center space-x-6">
          <h2 className="text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-purple-400 to-cyan-300">
            {t('brandName')}
          </h2>

          {/* MENU BUTTONS */}
          <div className="hidden md:flex items-center space-x-2">
            {menuItems.map((item) => (
              <button
                key={item.key}
                onClick={() => {
                  setPage(item.key);
                  if (item.key !== 'generator') setActiveTool(null);
                }}
                className={`px-3 py-2 rounded-lg text-sm font-medium transition-all
                  ${
                    page === item.key
                      ? 'bg-white/15 text-white'
                      : 'text-purple-200 hover:text-white hover:bg-white/10'
                  }`}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center space-x-4">
          <LanguageSwitcher />
          {isAuthenticated ? (
            <UserProfile />
          ) : (
            <button
              onClick={() => setShowAuthModal(true)}
              className="bg-gradient-to-r from-purple-500 to-cyan-500 text-white font-semibold py-2 px-6 rounded-lg hover:from-purple-600 hover:to-cyan-600 transition-all duration-200 transform hover:scale-105"
            >
              {t('navigation.signIn')}
            </button>
          )}
        </div>
      </nav>

      <main className="relative z-10 flex flex-col items-center justify-center min-h-[calc(100vh-100px)] p-4 sm:p-8">
        {page === 'home' ? (
          <>
            <header className="text-center mb-12">
              <h1 className="text-5xl md:text-7xl font-extrabold tracking-tighter bg-clip-text text-transparent bg-gradient-to-r from-purple-400 to-cyan-300">
                {t('dashboard.title')}
              </h1>
              <p className="mt-4 text-lg text-purple-200 max-w-2xl mx-auto">
                {t('dashboard.subtitle')}
              </p>
            </header>

            <RequestInput
              prompt={prompt}
              setPrompt={setPrompt}
              audioUrl={audioUrl}
              setAudioUrl={setAudioUrl}
              onAuthRequired={handleAuthRequired}
              isAuthenticated={isAuthenticated}
            />

            <div className="w-full max-w-7xl grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-8">
              {tools.map((tool) => (
                <ToolCard key={tool.id} tool={tool} onClick={handleCardClick} isLocked={false} />
              ))}
            </div>
          </>
        ) : page === 'information' ? (
          <div className="w-full max-w-4xl">
            <h1 className="text-4xl font-bold mb-4">Information</h1>
            <p className="text-purple-200">
              This is a placeholder page. Next we will add real content and connect it to admin editor.
            </p>
          </div>
        ) : page === 'news' ? (
          <div className="w-full max-w-4xl">
            <h1 className="text-4xl font-bold mb-4">News / Blog</h1>
            <p className="text-purple-200">
              Placeholder for blog/news list. Next we will connect it to admin panel (text + images).
            </p>
          </div>
        ) : page === 'instruction' ? (
          <div className="w-full max-w-4xl">
            <h1 className="text-4xl font-bold mb-4">Instruction</h1>
            <p className="text-purple-200">Placeholder for instructions.</p>
          </div>
        ) : page === 'payment' ? (
          <div className="w-full max-w-4xl">
            <h1 className="text-4xl font-bold mb-4">Payment</h1>
            <p className="text-purple-200">Placeholder for payment page.</p>
          </div>
        ) : page === 'veo-test' ? (
          <div className="w-full max-w-6xl">
            <button
              onClick={() => setPage('home')}
              className="mb-4 text-purple-300 hover:text-white transition-colors"
            >
              ← Back to Home
            </button>
            <div className="text-white text-center">VEO Test Page - Component Disabled for Debug</div>
          </div>
        ) : activeTool ? (
          <VideoGenerator tool={activeTool} initialPrompt={prompt} onBack={handleBackToHome} />
        ) : null}
      </main>

      <AuthModal isOpen={showAuthModal} onClose={() => setShowAuthModal(false)} />
    </div>
  );
};

const App: React.FC = () => {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
};

export default App;
