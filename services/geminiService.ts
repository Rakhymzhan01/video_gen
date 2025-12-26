
import { GoogleGenAI } from "@google/genai";

const API_KEY = process.env.API_KEY;

if (!API_KEY) {
  throw new Error("API_KEY environment variable not set.");
}

const ai = new GoogleGenAI({ apiKey: API_KEY });

const fileToBase64 = (file: File): Promise<string> => {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.readAsDataURL(file);
    reader.onload = () => {
      const result = reader.result as string;
      // remove "data:*/*;base64," prefix
      resolve(result.split(',')[1]);
    };
    reader.onerror = (error) => reject(error);
  });
};

const pollOperation = async <T,>(operation: any): Promise<any> => {
  let currentOperation = operation;
  while (!currentOperation.done) {
    await new Promise(resolve => setTimeout(resolve, 10000));
    currentOperation = await ai.operations.getVideosOperation({ operation: currentOperation });
  }
  return currentOperation;
};

export const generateVideo = async (prompt: string, imageFile?: File | null): Promise<string> => {
  try {
    let initialOperation;

    if (imageFile) {
      const base64Image = await fileToBase64(imageFile);
      initialOperation = await ai.models.generateVideos({
        model: 'veo-3.1-fast-generate-preview',
        prompt: prompt,
        image: {
          imageBytes: base64Image,
          mimeType: imageFile.type,
        },
        config: {
          numberOfVideos: 1,
        },
      });
    } else {
      initialOperation = await ai.models.generateVideos({
        model: 'veo-3.1-fast-generate-preview',
        prompt: prompt,
        config: {
          numberOfVideos: 1,
        },
      });
    }

    const completedOperation = await pollOperation(initialOperation);

    const downloadLink = completedOperation.response?.generatedVideos?.[0]?.video?.uri;

    if (!downloadLink) {
      throw new Error("Video generation failed: No download link found.");
    }

    const videoResponse = await fetch(`${downloadLink}&key=${API_KEY}`);
    if (!videoResponse.ok) {
        throw new Error(`Failed to download video: ${videoResponse.statusText}`);
    }

    const videoBlob = await videoResponse.blob();
    const videoUrl = URL.createObjectURL(videoBlob);
    return videoUrl;

  } catch (error) {
    console.error("Error generating video:", error);
    if (error instanceof Error) {
        throw new Error(`Video generation failed: ${error.message}`);
    }
    throw new Error("An unknown error occurred during video generation.");
  }
};
