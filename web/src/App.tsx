import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import Layout from './components/Layout';
import AssetDetail from './pages/AssetDetail';
import Home from './pages/Home';
import Library from './pages/Library';
import Settings from './pages/Settings';
import SearchAgent from './pages/SearchAgent';

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Home />} />
          <Route path="library" element={<Library />} />
          <Route path="search" element={<SearchAgent />} />
          <Route path="assets" element={<Navigate to="/library" replace />} />
          <Route path="assets/:assetId" element={<AssetDetail />} />
          <Route path="settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
