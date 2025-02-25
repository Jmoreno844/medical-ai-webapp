React 15 Guidelines
Component Structure
Use class components for stateful logic since hooks are unavailable in React 15.
Use functional components for stateless, presentational UI.
State Management
Manage state with setState; avoid direct state mutation.
Pass props immutably to prevent unintended side effects.
Event Handling
Bind event handlers in the constructor to maintain the correct this context.
javascript
Ajuste
Copiar
constructor(props) {
  super(props);
  this.handleClick = this.handleClick.bind(this);
}
Lifecycle Methods
Use componentDidMount for initial data fetching and setup.
Use componentDidUpdate to handle prop or state changes.
Use componentWillUnmount for cleanup (e.g., removing event listeners).
Performance
Minimize re-renders using shouldComponentUpdate or extend PureComponent for shallow prop and state comparisons.
Next.js Guidelines
Routing
Use file-based routing in the pages directory.
For dynamic routes, use brackets (e.g., pages/posts/[id].js).
API Routes
Secure API routes by validating inputs and using authentication middleware.
Example of input validation in an API route:
javascript
Ajuste
Copiar
export default function handler(req, res) {
  const { name } = req.body;
  if (!name || typeof name !== 'string') {
    return res.status(400).json({ error: 'Invalid name' });
  }
  // Proceed with sanitized input
}
Data Fetching
Use getServerSideProps for server-side rendering (SSR).
Use getStaticProps for static generation.
Ensure secure data fetching by validating and sanitizing data from external sources.
javascript
Ajuste
Copiar
export async function getServerSideProps(context) {
  const res = await fetch('https://api.example.com/data');
  const data = await res.json();
  return { props: { data } };
}
Security Best Practices
Preventing XSS
Sanitize user input using libraries like DOMPurify to prevent cross-site scripting (XSS).
javascript
Ajuste
Copiar
import DOMPurify from 'dompurify';
const cleanHtml = DOMPurify.sanitize(dirtyHtml);
Avoid dangerouslySetInnerHTML unless absolutely necessary and always sanitize content.
User Input Handling
Validate and sanitize all user inputs on the server side.
Use HTTPS to encrypt data in transit.
Authentication and Authorization
Implement secure authentication using JWT or sessions.
Protect routes and API endpoints with authentication middleware.
Server-Side Rendering (SSR)
In Next.js, ensure that sensitive data is not exposed during SSR by carefully managing what is passed to the client.
Coding Standards
Code Organization
Keep components small and focused on a single responsibility.
Organize files logically: components, pages, utilities, etc.
Naming Conventions
Use camelCase for variables and functions.
Use PascalCase for components and classes.
Error Handling
Use try-catch blocks in API routes to handle errors gracefully.
Implement React error boundaries to catch and handle UI errors.
Testing
Write unit tests for components and API routes using tools like Jest and React Testing Library.
Performance Optimizations
Code Splitting
Use dynamic imports in Next.js to split code and reduce initial load times.
javascript
Ajuste
Copiar
const DynamicComponent = dynamic(() => import('../components/DynamicComponent'));
Image Optimization
Use Next.js's Image component for automatic image optimization.
Minimize Re-renders
In React 15, use shouldComponentUpdate or extend PureComponent to prevent unnecessary re-renders.