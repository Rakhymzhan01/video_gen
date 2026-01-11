
import React from 'react';

interface GeneratedVideoProps {
  videoUrl: string;
  onGenerateAnother: () => void;
}

const GeneratedVideo: React.FC<GeneratedVideoProps> = ({ videoUrl, onGenerateAnother }) => {
  return (
    <div className="text-center space-y-6">
      <h2 className="text-2xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-green-300 to-blue-400">
        Your Video is Ready!
      </h2>
      <video
        src={videoUrl}
        controls
        autoPlay
        loop
        className="w-full rounded-lg shadow-lg border border-gray-700"
      >
        Your browser does not support the video tag.
      </video>
      <button
        onClick={onGenerateAnother}
        className="bg-indigo-600 text-white font-bold py-3 px-6 rounded-lg hover:bg-indigo-700 transition-all duration-300 transform hover:scale-105"
      >
        Generate Another Video
      </button>
    </div>
  );
};

export default GeneratedVideo;
