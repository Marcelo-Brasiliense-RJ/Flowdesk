import { Link, useLocation } from "react-router-dom";
import ProjectLayout, { useProject } from "../components/ProjectLayout";
import SmartChat from "../components/SmartChat";

/**
 * Smart Chat de um projeto existente. Destino do "Continuar no chat" do
 * Assistente (Pedido): a criação/ajuste da automação acontece aqui, e o
 * SmartChat redireciona de volta ao Assistente quando a automação fica pronta.
 */
export default function ProjectChat() {
  const { id, project } = useProject();
  const loc = useLocation();
  const draft = (loc.state as { draft?: string } | null)?.draft;

  return (
    <ProjectLayout project={project}>
      <div className="flex h-full flex-col">
        <div className="glass flex items-center justify-between border-b border-line px-5 py-2.5">
          <div className="min-w-0">
            <div className="text-[11px] uppercase tracking-wide text-ink3">Projeto</div>
            <div className="truncate font-semibold text-ink">{project?.name || "..."}</div>
          </div>
          <Link to={`/projects/${id}/assistente`} className="btn-outline py-1.5 text-sm">
            ← Voltar ao pedido
          </Link>
        </div>
        <div className="min-h-0 flex-1 overflow-hidden">
          <SmartChat
            key={id}
            projectId={id}
            initialInput={draft}
            onApplied={() => {}}
            centered
          />
        </div>
      </div>
    </ProjectLayout>
  );
}
