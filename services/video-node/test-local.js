const { GoogleGenAI } = require('@google/genai');

const API_KEY = "AIzaSyBkhxmhvxHoLGfhyCVJv8ZdBeg4HfcPjHQ";

async function testVEO() {
    console.log('🧪 Testing VEO API integration...');
    
    try {
        const ai = new GoogleGenAI({ apiKey: API_KEY });
        
        console.log('✅ GoogleGenAI instance created');
        
        // Test with a simple prompt
        const prompt = "A cute cat playing with a ball of yarn";
        console.log(`📝 Prompt: ${prompt}`);
        
        console.log('🚀 Starting video generation...');
        
        const initialOperation = await ai.models.generateVideos({
            model: 'veo-3.1-fast-generate-preview',
            prompt: prompt,
            config: {
                numberOfVideos: 1,
            },
        });
        
        console.log('✅ Video generation started!');
        console.log('📄 Operation:', JSON.stringify(initialOperation, null, 2));
        
        // Start polling
        console.log('⏳ Starting polling for completion...');
        let currentOperation = initialOperation;
        let attempts = 0;
        const maxAttempts = 20; // 20 attempts * 10 seconds = ~3 minutes max
        
        while (!currentOperation.done && attempts < maxAttempts) {
            console.log(`🔄 Poll attempt ${attempts + 1}/${maxAttempts}...`);
            await new Promise(resolve => setTimeout(resolve, 10000)); // 10 second delay
            
            currentOperation = await ai.operations.getVideosOperation({ 
                operation: currentOperation 
            });
            
            console.log(`📊 Status: ${currentOperation.done ? 'DONE' : 'PROCESSING'}`);
            attempts++;
        }
        
        if (currentOperation.done) {
            console.log('🎉 Video generation completed!');
            console.log('📄 Final operation:', JSON.stringify(currentOperation, null, 2));
            
            const downloadLink = currentOperation.response?.generatedVideos?.[0]?.video?.uri;
            
            if (downloadLink) {
                console.log('🔗 Download link:', downloadLink);
                console.log('✅ SUCCESS! Real VEO video generated');
            } else {
                console.log('❌ No download link found');
            }
        } else {
            console.log('⏰ Timeout - video generation took too long');
        }
        
    } catch (error) {
        console.error('❌ Error:', error.message);
        console.error('📋 Full error:', error);
    }
}

testVEO();