'use client';
import { cn } from '@/lib/utils';
import mermaid from 'mermaid';
import { useTranslations } from 'next-intl';
import { useTheme } from 'next-themes';
import panzoom from 'panzoom';
import { useCallback, useEffect, useRef, useState } from 'react';
import './chart-mermaid.css';
import { Card } from './ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from './ui/tabs';

export const ChartMermaid = ({ children }: { children: string }) => {
  const [svg, setSvg] = useState('');
  const { resolvedTheme } = useTheme();
  const [error, setError] = useState<boolean>(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const [id, setId] = useState<string>();

  const components_dmermaid = useTranslations('components.dmermaid');

  const [tab, setTab] = useState<string>('graph');

  const renderMermaid = useCallback(async () => {
    const isDark = resolvedTheme === 'dark';

    try {
      mermaid.initialize({
        startOnLoad: true,
        theme: isDark ? 'dark' : 'neutral',
        securityLevel: 'loose',
        themeVariables: {
          // primaryColor: '#0165ca',
          // primaryTextColor: '#fff',
          fontSize: 'inherit',
          labelBkg: 'transparent',
          lineColor: 'var(--input)',

          // Flowchart Variables
          nodeBorder: 'var(--border)',
          clusterBkg: 'var(--card)',
          clusterBorder: 'var(--input)',
          defaultLinkColor: 'var(--input)',
          edgeLabelBackground: 'transparent',
          titleColor: 'var(--muted-foreground)',
          nodeTextColor: 'var(--card-foreground)',
        },
        themeCSS: '.labelBkg { background: none; }',
        flowchart: {},
      });
      const { svg } = await mermaid.render(`mermaid-container-${id}`, children);
      setSvg(svg);
      setError(false);
    } catch (err) {
      console.log(err);
      setError(true);
    }
  }, [children, id, resolvedTheme]);

  useEffect(() => {
    renderMermaid();
  }, [renderMermaid]);

  useEffect(() => {
    setId(String((Math.random() * 100000).toFixed(0)));
  }, []);

  useEffect(() => {
    if (containerRef.current) {
      panzoom(containerRef.current, {
        minZoom: 0.5,
        maxZoom: 5,
      });
    }
  }, []);

  return (
    <>
      <Tabs value={tab} className="font-sans" onValueChange={setTab}>
        <TabsList className="w-full">
          <TabsTrigger value="graph">
            {components_dmermaid('graph')}
          </TabsTrigger>
          <TabsTrigger value="data">{components_dmermaid('data')}</TabsTrigger>
        </TabsList>
        <TabsContent
          value="graph"
          forceMount
          className={tab === 'graph' ? 'block' : 'hidden'}
        >
          <Card className="my-2 min-h-80 cursor-move overflow-hidden rounded-md p-4">
            <div
              ref={containerRef}
              data-error={error}
              className={`mermaid-container-${id} flex justify-center`}
              dangerouslySetInnerHTML={{
                __html: svg,
              }}
            />
          </Card>
        </TabsContent>
        <TabsContent value="data">
          <code className={cn('hljs language-mermaid my-2 rounded-md text-sm')}>
            {children}
          </code>
        </TabsContent>
      </Tabs>
    </>
  );
};
