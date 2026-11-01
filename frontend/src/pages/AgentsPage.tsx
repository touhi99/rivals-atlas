import { useSearchParams } from 'react-router-dom'
import InsightsView from '@/components/InsightsView'
import Layout from '@/components/Layout'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { AskChat } from '@/pages/AskPage'

/** Everything that needs a model, apart from the dashboard: the chat and the agents' analysis. */
export default function AgentsPage() {
  const [params, setParams] = useSearchParams()
  const tab = params.get('tab') === 'insights' ? 'insights' : 'ask'
  return (
    <Layout title="Agents" bar={false}>
      <Tabs className="gap-4" value={tab} onValueChange={(v) => setParams(v === 'insights' ? { tab: 'insights' } : {}, { replace: true })}>
        <TabsList>
          <TabsTrigger value="ask">Ask</TabsTrigger>
          <TabsTrigger value="insights">Insights</TabsTrigger>
        </TabsList>
        <TabsContent value="ask"><AskChat /></TabsContent>
        <TabsContent value="insights"><InsightsView /></TabsContent>
      </Tabs>
    </Layout>
  )
}
