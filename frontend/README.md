# Verseo Frontend

React-based UI for the SEO Domain Checker application.

## Tech Stack

- **React 18** - UI framework
- **TypeScript** - Type safety
- **Vite** - Build tool and dev server
- **Tailwind CSS** - Styling
- **Recharts** - Data visualization
- **Lucide React** - Icons

## Getting Started

### Install Dependencies

```bash
npm install
```

### Development

Start the development server (runs on http://localhost:3000):

```bash
npm run dev
```

The dev server includes a proxy to forward `/api` requests to the backend at `http://192.168.0.11:8000`.

### Build for Production

```bash
npm run build
```

The built files will be in the `dist/` directory.

### Preview Production Build

```bash
npm run preview
```

## Project Structure

```
frontend/
├── src/
│   ├── App.tsx          # Main application component
│   ├── main.tsx         # Entry point
│   └── index.css        # Global styles with Tailwind
├── index.html           # HTML template
├── package.json         # Dependencies and scripts
├── vite.config.ts       # Vite configuration
├── tsconfig.json        # TypeScript configuration
├── tailwind.config.js   # Tailwind CSS configuration
└── postcss.config.js    # PostCSS configuration
```

## Features

- **Domain Management** - View and manage SEO domains
- **Advanced Filtering** - Filter by status, topic, country, price, DR, and more
- **Sorting** - Sort by various metrics
- **Keyboard Shortcuts** - Quick actions (A: OK, S: Review, D: Reject, O: Open)
- **Dark Mode** - Toggle between light and dark themes
- **Preview Sidebar** - Quick evidence preview for each domain
- **Responsive Design** - Works on desktop and mobile devices

## API Integration

The frontend requires the `VITE_API_URL` environment variable to connect to the backend API.

### Local Development
Create a `.env` file in the `frontend/` directory:

```env
VITE_API_URL=http://localhost:8000
```

Then start the dev server:

```bash
npm run dev
```

### Production Deployment

#### Option 1: Build-time configuration
Set environment variable when building:

```bash
VITE_API_URL=https://api.example.com:8000 npm run build
```

#### Option 2: Docker build argument
```bash
docker build --build-arg VITE_API_URL=https://api.example.com:8000 -t frontend .
```

#### Option 3: Docker Compose
```yaml
services:
  frontend:
    build:
      context: ./frontend
      args:
        VITE_API_URL: https://api.example.com:8000
    ports:
      - "80:80"
```

### Examples

**Same host (different ports):**
```env
VITE_API_URL=http://192.168.1.100:8000
```

**Different host:**
```env
VITE_API_URL=https://backend.example.com:8000
```

**Production with HTTPS:**
```env
VITE_API_URL=https://api.yourdomain.com
```

## Customization

- Modify `tailwind.config.js` for theme customization
- Update API endpoints in the components as needed
- Add environment variables in `.env` files

