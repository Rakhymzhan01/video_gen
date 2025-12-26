import React, { useState, useCallback, useEffect } from 'react';
import { GenerationStatus, GenerationState } from '../types';
import { generateVideo } from '../services/geminiService';
import Spinner from './Spinner';
import GeneratedVideo from './GeneratedVideo';
import FileInput from './FileInput';

const LOADING_MESSAGES = [
    "Warming up the video engine...",
    "Compositing scenes...",
    "Rendering pixels...",
    "Applying cinematic magic...",
    "Adding final touches...",
    "Almost there, polishing the masterpiece..."
];

const VideoGenerator: React.FC = () => {
    const [prompt, setPrompt] = useState<string>('');
    const [imageFile, setImageFile] = useState<File | null>(null);
    const [imagePreviewUrl, setImagePreviewUrl] = useState<string | null>(null);
    const [generationState, setGenerationState] = useState<GenerationState>({ status: GenerationStatus.IDLE });
    const [loadingMessage, setLoadingMessage] = useState(LOADING_MESSAGES[0]);

    // Fix: Refactored useEffect to correctly handle conditional interval setup and cleanup.
    // This resolves the 'NodeJS.Timeout' type error by using type inference and prevents a potential runtime error.
    useEffect(() => {
        if (generationState.status === GenerationStatus.GENERATING) {
            const interval = setInterval(() => {
                setLoadingMessage(prev => {
                    const currentIndex = LOADING_MESSAGES.indexOf(prev);
                    const nextIndex = (currentIndex + 1) % LOADING_MESSAGES.length;
                    return LOADING_MESSAGES[nextIndex];
                });
            }, 3000);
            return () => {
                clearInterval(interval);
            };
        }
    }, [generationState.status]);


    const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0];
        if (file) {
            setImageFile(file);
            const previewUrl = URL.createObjectURL(file);
            setImagePreviewUrl(previewUrl);
        }
    };

    const removeImage = () => {
        setImageFile(null);
        if (imagePreviewUrl) {
            URL.revokeObjectURL(imagePreviewUrl);
            setImagePreviewUrl(null);
        }
    };

    const handleGenerate = useCallback(async () => {
        if (!prompt.trim()) {
            setGenerationState({ status: GenerationStatus.ERROR, error: "Prompt cannot be empty." });
            return;
        }
        setGenerationState({ status: GenerationStatus.GENERATING });
        setLoadingMessage(LOADING_MESSAGES[0]);

        try {
            const videoUrl = await generateVideo(prompt, imageFile);
            setGenerationState({ status: GenerationStatus.SUCCESS, videoUrl });
        } catch (error) {
            const errorMessage = error instanceof Error ? error.message : "An unknown error occurred.";
            setGenerationState({ status: GenerationStatus.ERROR, error: errorMessage });
        }
    }, [prompt, imageFile]);

    const resetState = () => {
        setPrompt('');
        removeImage();
        setGenerationState({ status: GenerationStatus.IDLE });
    };

    const isGenerating = generationState.status === GenerationStatus.GENERATING;

    return (
        <div className="w-full max-w-4xl p-6 md:p-8 bg-gray-800/50 backdrop-blur-sm border border-gray-700 rounded-2xl shadow-2xl transition-all duration-300">
            {generationState.status === GenerationStatus.IDLE && (
                <div className="space-y-6">
                    <div>
                        <label htmlFor="prompt" className="block text-sm font-medium text-gray-300 mb-2">Your Video Idea</label>
                        <textarea
                            id="prompt"
                            rows={4}
                            className="w-full bg-gray-900/50 border border-gray-600 rounded-lg p-3 text-gray-200 focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-colors"
                            placeholder="e.g., A neon hologram of a cat driving at top speed"
                            value={prompt}
                            onChange={(e) => setPrompt(e.target.value)}
                        />
                    </div>

                    <div className="flex items-center gap-4">
                        <FileInput onChange={handleImageChange} disabled={!!imageFile} />
                         {imagePreviewUrl && (
                             <div className="relative">
                                <img src={imagePreviewUrl} alt="Preview" className="h-20 w-20 object-cover rounded-lg" />
                                <button
                                    onClick={removeImage}
                                    className="absolute -top-2 -right-2 bg-red-500 text-white rounded-full h-6 w-6 flex items-center justify-center text-xs hover:bg-red-600 transition-colors"
                                    aria-label="Remove image"
                                >
                                    &times;
                                </button>
                             </div>
                         )}
                    </div>
                    
                    <button
                        onClick={handleGenerate}
                        disabled={isGenerating || !prompt.trim()}
                        className="w-full bg-indigo-600 text-white font-bold py-3 px-4 rounded-lg hover:bg-indigo-700 disabled:bg-gray-600 disabled:cursor-not-allowed transition-all duration-300 transform hover:scale-105"
                    >
                        Generate Video
                    </button>
                </div>
            )}

            {generationState.status === GenerationStatus.GENERATING && (
                <div className="text-center py-12">
                    <Spinner />
                    <p className="mt-4 text-lg font-semibold text-gray-300">Generating your video...</p>
                    <p className="mt-2 text-gray-400">This can take a few minutes. Please be patient.</p>
                    <p className="mt-4 text-cyan-400 font-mono transition-opacity duration-500">{loadingMessage}</p>
                </div>
            )}
            
            {generationState.status === GenerationStatus.SUCCESS && generationState.videoUrl && (
                <GeneratedVideo videoUrl={generationState.videoUrl} onGenerateAnother={resetState} />
            )}

            {(generationState.status === GenerationStatus.ERROR) && (
                 <div className="text-center py-8">
                    <p className="text-red-400 font-semibold">Generation Failed</p>
                    <p className="text-gray-400 mt-2">{generationState.error}</p>
                    <button
                        onClick={() => setGenerationState({ status: GenerationStatus.IDLE })}
                        className="mt-6 bg-gray-600 text-white font-bold py-2 px-4 rounded-lg hover:bg-gray-700 transition-colors"
                    >
                        Try Again
                    </button>
                </div>
            )}
        </div>
    );
};

export default VideoGenerator;