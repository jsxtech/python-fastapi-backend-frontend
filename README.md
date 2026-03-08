# FastAPI Inventory Manager

> ⚠️ **SAMPLE PROJECT - NOT PRODUCTION READY**  
> This is a demonstration/learning project showcasing FastAPI backend capabilities with a basic single-page HTML frontend for API testing. It is NOT intended for production use.

Full-stack inventory management system with FastAPI backend and vanilla JavaScript frontend.

## Features

### Core Functionality
- ✅ **CRUD Operations** - Create, Read, Update, Delete items
- ✅ **Authentication** - JWT-based login system with token persistence
- ✅ **Real-time Updates** - WebSocket notifications for live data sync
- ✅ **Persistent Storage** - JSON file-based database with auto-save

### Item Management
- 📦 **Item Fields**: name, price, quantity, description, category, tags, stock status
- 🔍 **Advanced Search**: Filter by name, description, quantity range, tags
- 📊 **Sorting**: Sort by name, price (ascending/descending), quantity
- 🏷️ **Category Management**: Organize items by categories
- 🔖 **Tag System**: Flexible tagging for better organization
- 📋 **Duplicate Items**: Clone items with one click
- ⚠️ **Low Stock Alerts**: Automatic alerts for items with quantity < 5
- ✅ **Stock Status Icons**: Visual indicators for in-stock/out-of-stock items

### Bulk Operations
- ☑️ **Multi-select Mode**: Select multiple items at once
- 📦 **Bulk Stock Updates**: Update stock status for multiple items
- 📥 **Batch Creation**: Create multiple items via API endpoint

### Data Export/Import
- 📄 **Export to JSON**: Full data export with structure
- 📊 **Export to CSV**: Spreadsheet-compatible format
- 📑 **Export to PDF**: Professional inventory reports
- 📥 **Import from JSON**: Restore or migrate data
- 💾 **Manual Backups**: Create timestamped backup files

### Analytics & Reporting
- 📈 **Dashboard Metrics** (5 key indicators):
  - Total items count
  - In-stock items count
  - Total inventory value
  - Low stock alerts count
  - Average item price
- 📊 **Price Distribution Charts**: Visual breakdown by price ranges
- 📋 **Category Analysis**: Value and count breakdown by category
- 🕒 **Activity Log**: Track all CRUD operations with timestamps
- 📑 **Summary Reports**: Comprehensive inventory overview
- 🔄 **Clickable Stats**: Click dashboard to refresh metrics

### UI/UX Features
- 🌙 **Dark Mode**: Toggle with persistence across sessions
- 🖨️ **Print-friendly Layout**: Optimized for printing
- 📱 **Responsive Design**: Works on desktop, tablet, and mobile
- 🎨 **Modern Gradient UI**: Beautiful purple gradient theme
- 🔔 **Real-time Notifications**: Toast notifications for actions
- 🪟 **Modal Dialogs**: Clean popups for reports and analytics
- 👤 **User Display**: Show logged-in username in header
- 🎯 **Empty States**: Helpful messages when no items exist
- ✨ **Hover Effects**: Interactive UI elements

### Advanced Features
- 🔄 **Background Tasks**: Async backup scheduling
- 🔌 **WebSocket Integration**: Live updates across clients
- 🎯 **Advanced Filtering**: Combine multiple filter criteria
- 📊 **Visual Bar Charts**: Data visualization in reports
- 💾 **Auto-save**: Automatic persistence on every change
- 🔢 **Quantity Tracking**: Full inventory quantity management
- 🏷️ **Multi-tag Support**: Add multiple tags per item

## Installation

```bash
# Clone or navigate to project directory
cd python-fastapi-backend-frontend

# Install dependencies
pip install -r requirements.txt
```

## Usage

```bash
# Start the server
uvicorn main:app --reload

# Access the application
# Open browser: http://localhost:8000
```

## Default Credentials

- **Username:** `admin`
- **Password:** `admin123`

Alternative user:
- **Username:** `user`
- **Password:** `user123`

## API Endpoints

### Authentication
- `POST /api/login` - User login (returns JWT token)

### Items CRUD
- `GET /api/items` - List all items (supports search, category, sort params)
- `GET /api/items/{id}` - Get single item by ID
- `POST /api/items` - Create new item
- `PUT /api/items/{id}` - Update existing item
- `DELETE /api/items/{id}` - Delete item
- `POST /api/items/batch` - Batch create multiple items
- `POST /api/duplicate/{id}` - Duplicate an existing item

### Search & Filter
- `GET /api/search/advanced` - Advanced search with multiple criteria
  - Query params: `q` (text), `min_qty`, `max_qty`, `tags`
- `GET /api/categories` - List all unique categories
- `GET /api/low-stock` - Get items with quantity < 5

### Analytics & Reports
- `GET /api/stats` - Dashboard statistics (5 metrics)
- `GET /api/analytics` - Price distribution and stock status analysis
- `GET /api/activity` - Activity log with timestamps (limit param)
- `GET /api/reports/summary` - Comprehensive summary report

### Export/Import
- `GET /api/export/csv` - Download CSV file
- `GET /api/export/pdf` - Download PDF report
- `POST /api/export` - Export to JSON format
- `POST /api/import` - Import from JSON file upload

### Bulk Operations
- `POST /api/bulk-update` - Update multiple items at once
  - Body: `{"item_ids": [1,2,3], "updates": {"in_stock": true}}`

### System
- `POST /api/backup/schedule` - Schedule background backup task
- `WS /ws` - WebSocket connection for real-time updates

## File Structure

```
.
├── main.py              # FastAPI backend (300+ lines)
├── auth.py              # JWT authentication module
├── requirements.txt     # Python dependencies (pinned versions)
├── items.json          # Database file (auto-created)
├── static/
│   └── index.html      # Frontend SPA (500+ lines)
└── README.md           # This file
```

## Technology Stack

**Backend:**
- FastAPI 0.109.0 - Modern async Python web framework
- Pydantic - Data validation and serialization
- PyJWT 2.8.0 - JWT token authentication
- ReportLab 4.0.9 - PDF generation
- WebSockets 12.0 - Real-time bidirectional communication
- Uvicorn - ASGI server with auto-reload

**Frontend:**
- Vanilla JavaScript (ES6+) - No frameworks, pure JS
- CSS3 - Gradients, animations, flexbox, grid
- LocalStorage API - Theme and auth persistence
- Fetch API - HTTP requests
- WebSocket API - Real-time updates

## Data Persistence

- **Items Database**: Stored in `items.json` with auto-save
- **Activity Log**: In-memory (resets on server restart)
- **Backups**: Manual/scheduled backups create timestamped files
- **User Sessions**: JWT tokens stored in localStorage
- **Theme Preference**: Dark mode setting persisted locally

## Browser Support

- ✅ Chrome/Edge 90+ (recommended)
- ✅ Firefox 88+
- ✅ Safari 14+
- ✅ Any modern browser with ES6+ and WebSocket support

## Security Notes

⚠️ **FOR DEVELOPMENT/LEARNING ONLY - NOT PRODUCTION READY**

This is a sample application designed to demonstrate FastAPI features and provide a simple frontend for API testing. It contains multiple security vulnerabilities and should NEVER be deployed to production.

**Critical Issues:**
- Hardcoded SECRET_KEY (change in production)
- Plain text passwords (implement bcrypt/argon2)
- CORS allows all origins (restrict in production)
- No rate limiting on endpoints
- No authentication middleware on most routes
- In-memory data storage (use PostgreSQL/MySQL)

**DO NOT use this code in production without:**
- Implementing proper security measures (see below)
- Using environment variables for secrets
- Implementing password hashing (bcrypt/argon2)
- Adding authentication middleware to all protected routes
- Restricting CORS to specific domains
- Adding rate limiting (slowapi)
- Using proper database with migrations (PostgreSQL/MySQL)
- Adding comprehensive input validation and sanitization
- Implementing proper logging and monitoring
- Adding HTTPS/SSL certificates
- Conducting security audit and penetration testing

## Purpose

This project serves as:
- **Learning Resource**: Understand FastAPI backend development
- **API Testing Tool**: Simple frontend to interact with REST APIs
- **Prototype Base**: Starting point for building production applications
- **Code Example**: Reference implementation of common patterns

## Features

**Total Features: 40+**

- 7 Core features
- 8 Item management features
- 3 Bulk operation features
- 5 Export/import features
- 7 Analytics features
- 9 UI/UX features
- 7 Advanced features

## API Documentation

Interactive API docs available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Future Enhancements

- [ ] Database migration (SQLite → PostgreSQL)
- [ ] Password hashing with bcrypt
- [ ] User roles and permissions (admin/viewer)
- [ ] Image uploads for items
- [ ] Barcode/QR code generation
- [ ] Email notifications for low stock
- [ ] Pagination for large datasets
- [ ] Advanced charts (Chart.js integration)
- [ ] Multi-language support (i18n)
- [ ] Mobile app (React Native)

## License

MIT License - Free to use and modify

**Disclaimer**: This software is provided "as is" without warranty of any kind. Use at your own risk. Not suitable for production environments without significant security enhancements.

## Author

Built with FastAPI and ❤️ as a learning/demonstration project

---

**Last Updated:** March 2026  
**Version:** 2.0.0  
**Status:** Sample/Demo Project Only
