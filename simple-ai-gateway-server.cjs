const express = require('express');
const app = express();
const port = 5052;

app.use(express.json());

app.get('/', (req, res) => {
  res.json({
    service: 'AI Gateway Service',
    description: 'AI workflow orchestration and automation gateway',
    version: '1.0.0',
    status: 'active',
    endpoints: {
      health: '/health',
      workflows: '/api/v1/workflows',
      agents: '/api/v1/agents'
    }
  });
});

app.get('/health', (req, res) => {
  res.json({
    status: 'healthy',
    service: 'AI Gateway Service',
    version: '1.0.0',
    timestamp: new Date().toISOString()
  });
});

app.get('/api/v1/workflows', (req, res) => {
  res.json({
    service: 'AI Gateway Service',
    version: '1.0.0',
    status: 'active',
    message: 'Workflow API available',
    data: []
  });
});

app.get('/api/v1/agents', (req, res) => {
  res.json({
    service: 'AI Gateway Service',
    version: '1.0.0',
    status: 'active',
    message: 'Agent API available',
    data: []
  });
});

app.listen(port, '0.0.0.0', () => {
  console.log(`AI Gateway Service running on port ${port}`);
});
