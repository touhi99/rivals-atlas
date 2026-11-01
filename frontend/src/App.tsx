import { Navigate, Route, Routes } from 'react-router-dom'
import { TooltipProvider } from '@/components/ui/tooltip'
import HeroesPage from '@/pages/HeroesPage'
import HeroDetailPage from '@/pages/HeroDetailPage'
import OverviewPage from '@/pages/OverviewPage'
import PatternsPage from '@/pages/PatternsPage'
import SquadPage from '@/pages/SquadPage'
import DataPage from '@/pages/DataPage'
import ExplorePage from '@/pages/ExplorePage'
import AgentsPage from '@/pages/AgentsPage'
import MapsPage from '@/pages/MapsPage'

export default function App() {
  return (
    <TooltipProvider delay={150}>
      <Routes>
        <Route path="/" element={<OverviewPage />} />
        <Route path="/heroes" element={<HeroesPage />} />
        <Route path="/heroes/:id" element={<HeroDetailPage />} />
        <Route path="/maps" element={<MapsPage />} />
        <Route path="/patterns" element={<PatternsPage />} />
        <Route path="/squad" element={<SquadPage />} />
        <Route path="/data" element={<DataPage />} />
        <Route path="/explore" element={<ExplorePage />} />
        <Route path="/agents" element={<AgentsPage />} />
        <Route path="/ask" element={<Navigate to="/agents" replace />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </TooltipProvider>
  )
}
