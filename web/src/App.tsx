import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Home from './pages/Home';
import VideoNote from './pages/VideoNote';
import VideoQA from './pages/VideoQA';
import SearchAgent from './pages/SearchAgent';
import DevTools from './pages/DevTools';
import MindMap from './pages/MindMap';
import KnowledgeCards from './pages/KnowledgeCards';
import History from './pages/History';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Home />} />
          <Route path="/note" element={<VideoNote />} />
          <Route path="/qa" element={<VideoQA />} />
          <Route path="/mindmap" element={<MindMap />} />
          <Route path="/cards" element={<KnowledgeCards />} />
          <Route path="/history" element={<History />} />
          <Route path="/search" element={<SearchAgent />} />
          <Route path="/dev-tools" element={<DevTools />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
