"use client";

import { useEffect, useRef } from "react";

/**
 * O campo de formas da tela de entrada — o padrão gráfico do manual em
 * movimento, como um pátio visto de cima.
 *
 * A forma é a mesma máscara de fotografia da marca: topo arredondado, base
 * curvada. Ela sobe devagar, e é só isso — nenhum dado, nenhuma informação,
 * nada que dependa de sessão. É decoração de marca, e por isso `aria-hidden`.
 *
 * ⛔ **Duas paradas obrigatórias, e as duas são de respeito ao usuário:**
 *
 * 1. `prefers-reduced-motion` — pinta um quadro e para. Não é "anima mais
 *    devagar": movimento contínuo em tela cheia é exatamente o que a
 *    preferência pede para não existir.
 * 2. `visibilitychange` — aba escondida não desenha. Um `requestAnimationFrame`
 *    rodando numa aba de fundo é bateria de alguém, e o navegador não garante
 *    que vai suspendê-lo.
 *
 * 📌 **Se pesar no mobile, corte ESTE componente e mantenha o gradiente.** O
 * símbolo e a cancela do botão carregam a marca sozinhos e custam quase nada —
 * o campo é o único pedaço caro da tela.
 */
export function EntryCanvas() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;

    const reduzido = window.matchMedia("(prefers-reduced-motion: reduce)");
    let largura = 0;
    let altura = 0;
    let formas: Forma[] = [];
    let frame = 0;
    let timerResize: ReturnType<typeof setTimeout> | undefined;

    /** Os tokens são lidos do CSS, nunca escritos aqui: a cor é do tenant. */
    function tokens() {
      const css = getComputedStyle(canvas!);
      return {
        base:
          css.getPropertyValue("--entry-shape").trim() || "rgba(90,90,90,.09)",
        luz:
          css.getPropertyValue("--entry-shape-lit").trim() ||
          "rgba(255,140,0,.13)",
        fundoA: css.getPropertyValue("--entry-canvas-1").trim() || "#E6E2DE",
        fundoB: css.getPropertyValue("--entry-canvas-2").trim() || "#F2F0EE",
      };
    }

    function silhueta(w: number, h: number, r: number) {
      const p = new Path2D();
      p.moveTo(r, 0);
      p.lineTo(w - r, 0);
      p.quadraticCurveTo(w, 0, w, r);
      p.lineTo(w, h * 0.74);
      p.quadraticCurveTo(w * 0.5, h * 1.14, 0, h * 0.74);
      p.lineTo(0, r);
      p.quadraticCurveTo(0, 0, r, 0);
      p.closePath();
      return p;
    }

    function semear() {
      const quantas = Math.max(7, Math.round((largura * altura) / 78000));
      formas = Array.from({ length: quantas }, () => {
        const w = 90 + Math.random() * 190;
        const h = w * (0.94 + Math.random() * 0.28);
        return {
          x: Math.random() * largura,
          y: Math.random() * (altura + 300) - 150,
          w,
          h,
          giro: Math.random() * 0.5 - 0.25,
          velocidade: 0.09 + Math.random() * 0.2,
          acesa: Math.random() < 0.22,
          caminho: silhueta(w, h, Math.min(w, h) * 0.19),
        };
      });
    }

    function medir() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const caixa = canvas!.getBoundingClientRect();
      largura = Math.max(caixa.width, 1);
      altura = Math.max(caixa.height, 1);
      canvas!.width = Math.round(largura * dpr);
      canvas!.height = Math.round(altura * dpr);
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
      semear();
    }

    function pintar(mover: boolean) {
      const { base, luz, fundoA, fundoB } = tokens();
      const gradiente = ctx!.createLinearGradient(0, 0, largura * 0.55, altura);
      gradiente.addColorStop(0, fundoA);
      gradiente.addColorStop(1, fundoB);
      ctx!.fillStyle = gradiente;
      ctx!.fillRect(0, 0, largura, altura);

      for (const forma of formas) {
        ctx!.save();
        ctx!.translate(forma.x, forma.y);
        ctx!.rotate(forma.giro * 0.06);
        ctx!.fillStyle = forma.acesa ? luz : base;
        ctx!.fill(forma.caminho);
        ctx!.restore();

        if (!mover) continue;
        forma.y -= forma.velocidade;
        if (forma.y + forma.h < -60) {
          forma.y = altura + 60 + Math.random() * 120;
          forma.x = Math.random() * largura;
        }
      }
    }

    function laco() {
      pintar(true);
      frame = requestAnimationFrame(laco);
    }

    function parar() {
      if (frame) cancelAnimationFrame(frame);
      frame = 0;
    }

    function reavaliar() {
      parar();
      // Aba escondida não desenha, e movimento reduzido pinta um quadro só.
      if (document.hidden) return;
      if (reduzido.matches) {
        pintar(false);
        return;
      }
      laco();
    }

    function aoRedimensionar() {
      clearTimeout(timerResize);
      timerResize = setTimeout(() => {
        medir();
        reavaliar();
      }, 140);
    }

    medir();
    reavaliar();

    window.addEventListener("resize", aoRedimensionar);
    document.addEventListener("visibilitychange", reavaliar);
    reduzido.addEventListener("change", reavaliar);

    return () => {
      parar();
      clearTimeout(timerResize);
      window.removeEventListener("resize", aoRedimensionar);
      document.removeEventListener("visibilitychange", reavaliar);
      reduzido.removeEventListener("change", reavaliar);
    };
  }, []);

  return (
    <canvas ref={ref} aria-hidden className="absolute inset-0 size-full" />
  );
}

type Forma = {
  x: number;
  y: number;
  w: number;
  h: number;
  giro: number;
  velocidade: number;
  acesa: boolean;
  caminho: Path2D;
};
