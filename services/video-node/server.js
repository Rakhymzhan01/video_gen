const express = require('express');
const cors = require('cors');
const multer = require('multer');
const { GoogleGenAI } = require('@google/genai');
const { v4: uuidv4 } = require('uuid');
const redis = require('redis');
require('dotenv').config({ path: '../../.env' });

const app = express();
const PORT = process.env.PORT || 8006;

// Middleware
app.use(cors());
app.use(express.json());
app.use(express.raw({ type: 'application/octet-stream', limit: '100mb' }));

// Multer for file uploads
const upload = multer({ 
  storage: multer.memoryStorage(),
  limits: { fileSize: 10 * 1024 * 1024 } // 10MB limit
});

// Google AI configuration
const API_KEY = process.env.GOOGLE_AI_API_KEY || process.env.VITE_API_KEY;
if (!API_KEY) {
  console.error('❌ GOOGLE_AI_API_KEY environment variable not set');
  process.exit(1);
}

const ai = new GoogleGenAI({ apiKey: API_KEY });

// Redis client configuration
const redisClient = redis.createClient({
  url: process.env.REDIS_URL || 'redis://localhost:6379'
});

// Connect to Redis
redisClient.on('error', (err) => {
  console.error('❌ Redis connection error:', err);
});

redisClient.on('connect', () => {
  console.log('✅ Connected to Redis');
});

// Initialize Redis connection
(async () => {
  try {
    await redisClient.connect();
  } catch (error) {
    console.error('❌ Failed to connect to Redis:', error);
  }
})();

// Helper function to convert file to base64
const fileToBase64 = (buffer) => {
  return buffer.toString('base64');
};

// Redis helper functions for operation management
const setOperationStatus = async (operationId, data) => {
  try {
    await redisClient.setEx(`video_op:${operationId}`, 3600, JSON.stringify(data)); // 1 hour expiry
    console.log(`📝 Stored operation ${operationId} in Redis`);
  } catch (error) {
    console.error('❌ Failed to store operation in Redis:', error);
  }
};

const getOperationStatus = async (operationId) => {
  try {
    const data = await redisClient.get(`video_op:${operationId}`);
    return data ? JSON.parse(data) : null;
  } catch (error) {
    console.error('❌ Failed to get operation from Redis:', error);
    return null;
  }
};

const deleteOperation = async (operationId) => {
  try {
    await redisClient.del(`video_op:${operationId}`);
    console.log(`🗑️ Deleted operation ${operationId} from Redis`);
  } catch (error) {
    console.error('❌ Failed to delete operation from Redis:', error);
  }
};

// Polling function for VEO operations
const pollOperation = async (operation) => {
  let currentOperation = operation;
  console.log('📹 Starting VEO operation polling...');
  
  while (!currentOperation.done) {
    console.log('⏳ Waiting 10 seconds before next poll...');
    await new Promise(resolve => setTimeout(resolve, 10000));
    
    try {
      currentOperation = await ai.operations.getVideosOperation({ operation: currentOperation });
      console.log('🔄 Operation status:', currentOperation.done ? 'DONE' : 'PROCESSING');
    } catch (error) {
      console.error('❌ Error polling operation:', error.message);
      throw error;
    }
  }
  
  return currentOperation;
};

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({ 
    status: 'healthy', 
    service: 'video-node-service',
    timestamp: new Date().toISOString()
  });
});

// Generate video endpoint
app.post('/generate', upload.single('image'), async (req, res) => {
  try {
    console.log('🎬 Starting video generation request');
    
    const { prompt, duration, resolution, provider } = req.body;
    const imageFile = req.file;
    
    if (!prompt || prompt.trim().length === 0) {
      return res.status(400).json({
        error: 'Prompt is required and cannot be empty'
      });
    }

    console.log('📝 Prompt:', prompt);
    console.log('📷 Image provided:', !!imageFile);
    
    // Generate operation ID
    const operationId = uuidv4();
    console.log('🆔 Operation ID:', operationId);

    // Store initial operation state in Redis
    await setOperationStatus(operationId, {
      id: operationId,
      status: 'processing',
      progress: 0,
      prompt: prompt,
      createdAt: new Date().toISOString(),
      imageProvided: !!imageFile,
      metadata: {
        provider: 'VEO3',
        model: 'veo-3.1-fast-generate-preview',
        real_api: true,
        node_service: true
      }
    });

    // Start video generation in background
    setImmediate(async () => {
      try {
        console.log('🚀 Starting VEO API call...');
        
        let initialOperation;

        if (imageFile) {
          console.log('📷 Image-to-video generation');
          const base64Image = fileToBase64(imageFile.buffer);
          
          initialOperation = await ai.models.generateVideos({
            model: 'veo-3.1-fast-generate-preview',
            prompt: prompt,
            image: {
              imageBytes: base64Image,
              mimeType: imageFile.mimetype,
            },
            config: {
              numberOfVideos: 1,
            },
          });
        } else {
          console.log('📝 Text-to-video generation');
          
          initialOperation = await ai.models.generateVideos({
            model: 'veo-3.1-fast-generate-preview',
            prompt: prompt,
            config: {
              numberOfVideos: 1,
            },
          });
        }

        console.log('✅ VEO API call initiated, starting polling...');

        // Update operation with VEO operation info in Redis
        const opData = await getOperationStatus(operationId);
        if (opData) {
          opData.veoOperation = initialOperation;
          opData.status = 'polling';
          opData.progress = 10;
          await setOperationStatus(operationId, opData);
        }

        // Poll for completion
        const completedOperation = await pollOperation(initialOperation);

        console.log('🎉 VEO generation completed!');
        console.log('📄 Full VEO response:', JSON.stringify(completedOperation, null, 2));

        // Try multiple possible paths for the download link
        let downloadLink = completedOperation.response?.generatedVideos?.[0]?.video?.uri;
        
        if (!downloadLink) {
          // Try alternative paths
          downloadLink = completedOperation.response?.generatedVideos?.[0]?.downloadUri;
        }
        
        if (!downloadLink) {
          // Try another alternative path
          downloadLink = completedOperation.response?.videos?.[0]?.uri;
        }
        
        if (!downloadLink) {
          // Try yet another alternative path
          downloadLink = completedOperation.response?.videos?.[0]?.downloadUri;
        }

        console.log('🔗 Found download link:', downloadLink);

        if (!downloadLink) {
          console.error('❌ No download link found. Full response structure:', JSON.stringify(completedOperation.response, null, 2));
          throw new Error('No download link found in VEO response');
        }

        console.log('📦 Downloading video from VEO...');

        // Download the video
        const fetch = (await import('node-fetch')).default;
        const videoResponse = await fetch(`${downloadLink}&key=${API_KEY}`);
        
        if (!videoResponse.ok) {
          throw new Error(`Failed to download video: ${videoResponse.statusText}`);
        }

        const videoBuffer = await videoResponse.buffer();
        console.log('✅ Video downloaded, size:', videoBuffer.length, 'bytes');

        // Update operation with success in Redis
        const finalOpData = await getOperationStatus(operationId);
        if (finalOpData) {
          finalOpData.status = 'completed';
          finalOpData.progress = 100;
          finalOpData.video_url = `data:video/mp4;base64,${videoBuffer.toString('base64')}`;
          finalOpData.completedAt = new Date().toISOString();
          finalOpData.downloadLink = downloadLink;
          // Remove large video buffer from Redis, keep only the data URL
          delete finalOpData.videoBuffer;
          await setOperationStatus(operationId, finalOpData);
        }

      } catch (error) {
        console.error('❌ VEO generation failed:', error.message);
        
        // Update operation with error in Redis
        const errorOpData = await getOperationStatus(operationId);
        if (errorOpData) {
          errorOpData.status = 'failed';
          errorOpData.error_message = error.message;
          errorOpData.failedAt = new Date().toISOString();
          await setOperationStatus(operationId, errorOpData);
        }
      }
    });

    // Return immediate response
    res.json({
      id: operationId,
      status: 'processing',
      progress_percentage: 0,
      estimated_completion_time: 90,
      metadata: {
        provider: 'VEO3',
        model: 'veo-3.1-fast-generate-preview',
        prompt: prompt,
        real_api: true,
        node_service: true
      }
    });

  } catch (error) {
    console.error('❌ Error in generate endpoint:', error.message);
    res.status(500).json({
      error: error.message,
      details: 'Failed to start video generation'
    });
  }
});

// Get video status endpoint
app.get('/:operationId/status', async (req, res) => {
  const { operationId } = req.params;
  console.log(`📊 Status check for: ${operationId}`);
  
  try {
    const operation = await getOperationStatus(operationId);

    if (!operation) {
      return res.status(404).json({
        error: 'Operation not found'
      });
    }

    console.log('📊 Status check for:', operationId, '- Status:', operation.status);

    res.json({
      id: operationId,
      status: operation.status,
      progress_percentage: operation.progress || 0,
      video_url: operation.video_url || null,
      error_message: operation.error_message || null,
      metadata: {
        provider: 'VEO3',
        model: 'veo-3.1-fast-generate-preview',
        prompt: operation.prompt,
        real_api: true,
        node_service: true,
        created_at: operation.createdAt,
        completed_at: operation.completedAt,
        image_provided: operation.imageProvided,
        download_link: operation.downloadLink
      }
    });
    
  } catch (error) {
    console.error('❌ Error getting operation status:', error);
    res.status(500).json({
      error: 'Internal server error',
      details: error.message
    });
  }
});

// Download video endpoint
app.get('/:operationId/download', async (req, res) => {
  const { operationId } = req.params;
  
  try {
    const operation = await getOperationStatus(operationId);

    if (!operation || !operation.video_url) {
      return res.status(404).json({
        error: 'Video not found or not ready'
      });
    }

    // Extract base64 data from data URL
    const base64Data = operation.video_url.split(',')[1];
    const videoBuffer = Buffer.from(base64Data, 'base64');
    
    res.set({
      'Content-Type': 'video/mp4',
      'Content-Disposition': `attachment; filename="veo-video-${operationId}.mp4"`,
      'Content-Length': videoBuffer.length
    });

    res.send(videoBuffer);
    
  } catch (error) {
    console.error('❌ Error downloading video:', error);
    res.status(500).json({
      error: 'Internal server error',
      details: error.message
    });
  }
});

// List operations endpoint (simplified for now)
app.get('/operations', (req, res) => {
  // TODO: Implement Redis-based operations listing if needed
  res.json({
    operations: [],
    total: 0,
    message: 'Operations listing not implemented with Redis yet'
  });
});

// Start server
app.listen(PORT, () => {
  console.log(`🎬 Video Node Service running on port ${PORT}`);
  console.log(`🔑 API Key configured: ${API_KEY ? 'YES' : 'NO'}`);
  console.log(`📊 Health check: http://localhost:${PORT}/health`);
  console.log(`🎥 Generate video: POST http://localhost:${PORT}/generate`);
  console.log(`📈 Check status: GET http://localhost:${PORT}/:id/status`);
});

// Graceful shutdown
process.on('SIGTERM', () => {
  console.log('🛑 Received SIGTERM, shutting down gracefully');
  process.exit(0);
});

process.on('SIGINT', () => {
  console.log('🛑 Received SIGINT, shutting down gracefully');
  process.exit(0);
});