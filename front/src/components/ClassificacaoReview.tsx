import { useMemo, useState } from "react";
import type {
  ClassificacaoReviewData,
  ContaPlano,
  GrupoClassificacao,
} from "../lib/types";

interface Escolha {
  conta: string | null; // codigo, "IGNORAR" ou null (pendente)
  confirmado: boolean;
  origem: "regra" | "ia" | "manual" | null;
  confianca?: number;
}

/** Revisão da classificação contábil antes de gerar a planilha do Domínio.
 *  Semáforo: verde = regra do usuário (passa direto); âmbar = sugestão de IA
 *  (exige confirmação); vermelho = sem sugestão (obriga escolher conta). */
export default function ClassificacaoReview({
  data,
  sugestoesIa,
  busy,
  onConfirm,
}: {
  data: ClassificacaoReviewData;
  /** padrao -> {conta_codigo, confianca}, vindas do endpoint classificar-grupos */
  sugestoesIa: Record<string, { conta_codigo: string; confianca: number }>;
  busy: boolean;
  onConfirm: (payload: {
    mapa: Record<string, string>;
    contaBanco: string;
    periodo: { inicio: string; fim: string };
    novasRegras: { padrao: string; conta_codigo: string; conta_nome: string }[];
  }) => void;
}) {
  const contasPorCodigo = useMemo(
    () => Object.fromEntries(data.contas.map((c) => [c.codigo, c])),
    [data.contas]
  );
  const [escolhas, setEscolhas] = useState<Record<string, Escolha>>(() => {
    const init: Record<string, Escolha> = {};
    for (const g of data.grupos) {
      if (g.origem === "regra" && g.conta) {
        init[g.padrao] = { conta: g.conta, confirmado: true, origem: "regra" };
      } else {
        const s = sugestoesIa[g.padrao];
        init[g.padrao] = s?.conta_codigo
          ? { conta: s.conta_codigo, confirmado: false, origem: "ia", confianca: s.confianca }
          : { conta: null, confirmado: false, origem: null };
      }
    }
    return init;
  });
  const [contaBanco, setContaBanco] = useState(data.conta_banco || "");
  const [inicio, setInicio] = useState(data.periodo_detectado.inicio);
  const [fim, setFim] = useState(data.periodo_detectado.fim);
  const [lembrar, setLembrar] = useState(true);

  function definir(padrao: string, conta: string) {
    setEscolhas((e) => ({
      ...e,
      [padrao]: { conta, confirmado: true, origem: "manual" },
    }));
  }
  function confirmarSugestao(padrao: string) {
    setEscolhas((e) => ({ ...e, [padrao]: { ...e[padrao], confirmado: true } }));
  }

  // --- Ações em lote ---
  function confirmarTodasIa() {
    setEscolhas((e) => {
      const next = { ...e };
      for (const g of data.grupos) {
        const cur = next[g.padrao];
        if (cur?.origem === "ia" && cur.conta && !cur.confirmado) {
          next[g.padrao] = { ...cur, confirmado: true };
        }
      }
      return next;
    });
  }
  function ignorarSemSugestao() {
    setEscolhas((e) => {
      const next = { ...e };
      for (const g of data.grupos) {
        if (!next[g.padrao]?.conta) {
          next[g.padrao] = { conta: "IGNORAR", confirmado: true, origem: "manual" };
        }
      }
      return next;
    });
  }
  const iaPendentes = data.grupos.filter((g) => {
    const e = escolhas[g.padrao];
    return e?.origem === "ia" && e.conta && !e.confirmado;
  }).length;
  const semSugestao = data.grupos.filter((g) => !escolhas[g.padrao]?.conta).length;

  const pendentes = data.grupos.filter((g) => {
    const e = escolhas[g.padrao];
    return !e?.conta || !e.confirmado;
  });
  const pronto = pendentes.length === 0 && !!contaBanco.trim();

  function confirmar() {
    const mapa: Record<string, string> = {};
    const novasRegras: { padrao: string; conta_codigo: string; conta_nome: string }[] = [];
    for (const g of data.grupos) {
      const e = escolhas[g.padrao];
      if (!e?.conta) continue;
      mapa[g.padrao] = e.conta;
      if (lembrar && e.origem !== "regra" && e.conta !== "IGNORAR") {
        novasRegras.push({
          padrao: g.padrao,
          conta_codigo: e.conta,
          conta_nome: contasPorCodigo[e.conta]?.nome || "",
        });
      }
    }
    if (lembrar && contaBanco && contaBanco !== data.conta_banco) {
      novasRegras.push({
        padrao: "_CONTA_BANCO",
        conta_codigo: contaBanco,
        conta_nome: "Conta do banco",
      });
    }
    onConfirm({ mapa, contaBanco, periodo: { inicio, fim }, novasRegras });
  }

  return (
    <div className="card p-4">
      <h4 className="text-sm font-bold text-ink">Revisão da classificação</h4>
      <p className="mt-0.5 text-xs text-ink2">
        {data.total_lancamentos} lançamentos em {data.grupos.length} grupos. Verde veio
        das suas regras; âmbar é sugestão da IA (confirme); vermelho precisa de conta.
      </p>

      <div className="mt-3 grid gap-2 sm:grid-cols-3">
        <label className="text-xs text-ink2">
          Conta do banco (lado banco)
          <ContaSelect contas={data.contas} value={contaBanco} onChange={setContaBanco} />
        </label>
        <label className="text-xs text-ink2">
          Competência: início
          <input
            className="input mt-1 py-1.5 text-sm"
            value={inicio}
            onChange={(e) => setInicio(e.target.value)}
            placeholder="dd/mm/aaaa"
          />
        </label>
        <label className="text-xs text-ink2">
          Competência: fim
          <input
            className="input mt-1 py-1.5 text-sm"
            value={fim}
            onChange={(e) => setFim(e.target.value)}
            placeholder="dd/mm/aaaa"
          />
        </label>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="text-xs font-medium text-ink2">Em lote:</span>
        <button
          type="button"
          onClick={confirmarTodasIa}
          disabled={iaPendentes === 0}
          className="rounded-md border border-line px-2 py-1 text-xs text-ink hover:bg-surface-2 disabled:opacity-40"
          title="Confirma todos os grupos com sugestão da IA (âmbar)"
        >
          Aceitar sugestões da IA ({iaPendentes})
        </button>
        <button
          type="button"
          onClick={ignorarSemSugestao}
          disabled={semSugestao === 0}
          className="rounded-md border border-line px-2 py-1 text-xs text-ink hover:bg-surface-2 disabled:opacity-40"
          title="Marca como ignorado todos os grupos sem conta (vermelho)"
        >
          Ignorar sem sugestão ({semSugestao})
        </button>
      </div>

      <div className="mt-3 max-h-80 space-y-2 overflow-auto pr-1">
        {data.grupos.map((g) => (
          <GrupoRow
            key={g.padrao}
            grupo={g}
            escolha={escolhas[g.padrao]}
            contas={data.contas}
            contasPorCodigo={contasPorCodigo}
            onEscolher={(c) => definir(g.padrao, c)}
            onConfirmar={() => confirmarSugestao(g.padrao)}
          />
        ))}
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-line pt-3">
        <label className="flex items-center gap-1.5 text-xs text-ink2">
          <input
            type="checkbox"
            checked={lembrar}
            onChange={(e) => setLembrar(e.target.checked)}
            className="h-3.5 w-3.5 accent-brand-600"
          />
          Lembrar destas escolhas para as próximas execuções
        </label>
        <button
          onClick={confirmar}
          disabled={!pronto || busy}
          className="btn-accent py-2 text-sm disabled:opacity-40"
          title={pronto ? "" : "Defina a conta do banco e resolva os grupos pendentes"}
        >
          {busy ? "Gerando…" : "Confirmar classificação e gerar planilha"}
        </button>
      </div>
      {!pronto && (
        <p className="mt-1 text-right text-xs text-warn2">
          {pendentes.length > 0 && `${pendentes.length} grupo(s) pendente(s). `}
          {!contaBanco.trim() && "Informe a conta do banco."}
        </p>
      )}
    </div>
  );
}

function GrupoRow({
  grupo,
  escolha,
  contas,
  contasPorCodigo,
  onEscolher,
  onConfirmar,
}: {
  grupo: GrupoClassificacao;
  escolha: Escolha;
  contas: ContaPlano[];
  contasPorCodigo: Record<string, ContaPlano>;
  onEscolher: (conta: string) => void;
  onConfirmar: () => void;
}) {
  const cor = !escolha?.conta
    ? { borderColor: "var(--err)", background: "var(--err-soft)" }
    : escolha.confirmado
      ? { borderColor: "var(--ok)", background: "var(--ok-soft)" }
      : { borderColor: "var(--warn2)", background: "var(--warn2-soft)" };
  const valor = grupo.total.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  return (
    <div className="flex min-h-[4.75rem] flex-col justify-between rounded-lg border p-2.5" style={cor}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-sm font-medium text-ink" title={grupo.exemplo}>
            {grupo.padrao || "(sem histórico)"}
          </div>
          <div className="text-[11px] text-ink2">
            {grupo.qtd} lançamento(s) · {valor} · {grupo.tipo === "credito" ? "entrada" : "saída"}
            {escolha?.origem === "regra" && " · sua regra"}
            {escolha?.origem === "ia" &&
              ` · IA ${escolha.confianca ? Math.round(escolha.confianca * 100) : 0}%`}
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <ContaSelect
            contas={contas}
            value={escolha?.conta === "IGNORAR" ? "" : escolha?.conta || ""}
            onChange={onEscolher}
            compact
          />
          {escolha?.conta && !escolha.confirmado && (
            <button onClick={onConfirmar} className="btn-accent px-2 py-1 text-xs">
              OK
            </button>
          )}
          <button
            onClick={() => onEscolher("IGNORAR")}
            className={`rounded-md px-2 py-1 text-xs ${
              escolha?.conta === "IGNORAR"
                ? "text-white"
                : "text-ink3 hover:bg-surface-2"
            }`}
            style={escolha?.conta === "IGNORAR" ? { background: "var(--neutral)" } : undefined}
            title="Não importar este grupo"
          >
            Ignorar
          </button>
        </div>
      </div>
      <div className="mt-1 truncate text-[11px] text-ink2">
        {escolha?.conta === "IGNORAR"
          ? "→ fora da planilha (ignorado)"
          : escolha?.conta
            ? `→ ${escolha.conta} ${contasPorCodigo[escolha.conta]?.nome || ""}`
            : "→ selecione a conta contábil"}
      </div>
    </div>
  );
}

function ContaSelect({
  contas,
  value,
  onChange,
  compact = false,
}: {
  contas: ContaPlano[];
  value: string;
  onChange: (codigo: string) => void;
  compact?: boolean;
}) {
  const [busca, setBusca] = useState("");
  const [aberto, setAberto] = useState(false);
  const filtradas = useMemo(() => {
    const q = busca.trim().toLowerCase();
    if (!q) return contas.slice(0, 30);
    return contas
      .filter(
        (c) =>
          c.nome.toLowerCase().includes(q) || c.codigo.includes(q) || c.classificacao.includes(q)
      )
      .slice(0, 30);
  }, [contas, busca]);
  return (
    <div className="relative">
      <input
        className={`input ${compact ? "w-48 py-1 text-xs" : "mt-1 py-1.5 text-sm"}`}
        placeholder={value ? `${value}` : "Buscar conta…"}
        value={busca}
        onFocus={() => setAberto(true)}
        onBlur={() => setTimeout(() => setAberto(false), 150)}
        onChange={(e) => {
          setBusca(e.target.value);
          setAberto(true);
        }}
      />
      {aberto && (
        <div className="absolute z-20 mt-1 max-h-48 w-72 overflow-auto rounded-lg border border-line bg-surface shadow-token-lg">
          {filtradas.map((c) => (
            <button
              key={c.codigo}
              type="button"
              onMouseDown={() => {
                onChange(c.codigo);
                setBusca("");
                setAberto(false);
              }}
              className="block w-full px-2.5 py-1.5 text-left text-xs hover:bg-surface-2"
            >
              <span className="font-mono text-brandv">{c.codigo}</span>{" "}
              <span className="text-ink2">{c.nome}</span>
              <span className="ml-1 text-ink3">{c.classificacao}</span>
            </button>
          ))}
          {filtradas.length === 0 && (
            <div className="px-2.5 py-2 text-xs text-ink3">Nenhuma conta encontrada.</div>
          )}
        </div>
      )}
    </div>
  );
}
