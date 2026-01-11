
import React from 'react';
import VideoGenerator from './components/VideoGenerator';
import Attribution from './components/Attribution';

const App: React.FC = () => {
  return (
    <div className="min-h-screen bg-gray-900 text-gray-200 flex flex-col items-center justify-center p-4 font-sans">
      <main className="w-full max-w-4xl flex-grow flex flex-col items-center justify-center">
        <header className="text-center mb-8">
          <h1 className="text-4xl md:text-5xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-indigo-400 to-cyan-400">
            ALDIS AI видео жасағыш!
          </h1>
          <p className="text-gray-400 mt-2">
            Bring your ideas to life with AI-powered video creation.
          </p>
        </header>
        <VideoGenerator />
      </main>
      <Attribution />
    </div>
  );
};

export default App;
