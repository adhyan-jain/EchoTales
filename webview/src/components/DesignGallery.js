import React, { useState } from 'react';
import Button from './ui/Button';
import { Card, CardBody } from './ui/Card';
import Label from './ui/Label';
import Input from './ui/Input';
import Divider from './ui/Divider';
import EvidenceBlock from './ui/EvidenceBlock';
import CharacterRow from './ui/CharacterRow';
import AudioPlayer from './ui/AudioPlayer';
import ManuscriptProgress from './ui/ManuscriptProgress';
import { EmptyState, LoadingState } from './ui/EmptyState';
import Modal from './ui/Modal';
import { useToast } from './ui/Toast';
import { applyTheme } from '../theme';

const SAMPLE_CHAPTERS = [
  { number: 1, status: 'found' },
  { number: 2, status: 'found' },
  { number: 3, status: 'found' },
  { number: 4, status: 'processing' },
  { number: 5, status: 'pending' },
];

export default function DesignGallery() {
  const [modalOpen, setModalOpen] = useState(false);
  const [theme, setTheme] = useState(document.documentElement.getAttribute('data-theme') || 'dark');
  const push = useToast();

  const toggleTheme = () => {
    const next = theme === 'dark' ? 'light' : 'dark';
    applyTheme(next);
    setTheme(next);
  };

  return (
    <div className="min-h-screen bg-bg font-sans text-text">
      <div className="mx-auto max-w-4xl px-8 py-14">
        <header className="flex items-end justify-between border-b border-border pb-6">
          <div>
            <div className="font-mono text-xs uppercase tracking-widest text-muted">EchoTales &middot; Design System</div>
            <h1 className="mt-2 font-display text-4xl text-text">The Archive Instrument</h1>
          </div>
          <Button variant="secondary" size="sm" onClick={toggleTheme}>
            {theme === 'dark' ? 'Paper' : 'Ink'} mode
          </Button>
        </header>

        <section className="mt-14">
          <Divider label="Typography" className="mb-6" />
          <div className="space-y-5">
            <div>
              <div className="font-mono text-xs text-muted mb-1">display &middot; Fraunces</div>
              <div className="font-display text-5xl text-text">Elena Voss</div>
            </div>
            <div>
              <div className="font-mono text-xs text-muted mb-1">heading &middot; display / md</div>
              <div className="font-display text-2xl text-text">Cast / 043</div>
            </div>
            <div>
              <div className="font-mono text-xs text-muted mb-1">body &middot; Source Sans 3</div>
              <div className="font-sans text-base text-text max-w-lg">
                The clan leader was never named directly in the opening chapters, and yet every
                deference paid to him made his position unmistakable.
              </div>
            </div>
            <div>
              <div className="font-mono text-xs text-muted mb-1">metadata &middot; JetBrains Mono</div>
              <div className="font-mono text-sm text-muted">CHAPTER 07 &middot; PAGE 83 &middot; CONFIDENCE 0.91</div>
            </div>
            <div>
              <div className="font-mono text-xs text-muted mb-1">quote &middot; Fraunces italic</div>
              <blockquote className="font-display italic text-xl text-text border-l-2 border-border pl-4">
                &ldquo;She entered wearing the green robes her mother once wore.&rdquo;
              </blockquote>
            </div>
          </div>
        </section>

        <section className="mt-14">
          <Divider label="Color" className="mb-6" />
          <div className="grid grid-cols-3 gap-3 sm:grid-cols-5">
            {[
              ['bg', 'bg-bg'], ['surface', 'bg-surface'], ['surface2', 'bg-surface2'],
              ['border', 'bg-border'], ['accent', 'bg-accent'], ['accent-2', 'bg-accent-2'],
              ['success', 'bg-success'], ['warning', 'bg-warning'], ['danger', 'bg-danger'],
            ].map(([name, cls]) => (
              <div key={name}>
                <div className={`h-12 border border-border ${cls}`} />
                <div className="mt-1 font-mono text-xs text-muted">{name}</div>
              </div>
            ))}
          </div>
        </section>

        <section className="mt-14">
          <Divider label="Buttons & labels" className="mb-6" />
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="primary">Approve sample</Button>
            <Button variant="secondary">Replace voice</Button>
            <Button variant="ghost">Edit reference</Button>
            <Button variant="danger">Cast is wrong</Button>
            <Button variant="primary" disabled>Disabled</Button>
          </div>
          <div className="mt-4 flex flex-wrap gap-4">
            <Label tone="accent">Principal</Label>
            <Label tone="neutral">Incidental</Label>
            <Label tone="success">Resolved</Label>
            <Label tone="warning">Needs review</Label>
            <Label tone="danger">Conflict</Label>
          </div>
        </section>

        <section className="mt-14">
          <Divider label="Inputs" className="mb-6" />
          <div className="max-w-sm space-y-3">
            <Input placeholder="Search the cast..." />
            <Input placeholder="Disabled" disabled />
          </div>
        </section>

        <section className="mt-14">
          <Divider label="Evidence block" className="mb-6" />
          <Card><CardBody>
            <EvidenceBlock
              trait="Green robes"
              source="Chapter 07 · Page 83"
              quote="She entered wearing the green robes her mother once wore, the hem still marked with travel dust."
            />
          </CardBody></Card>
        </section>

        <section className="mt-14">
          <Divider label="Cast row" className="mb-6" />
          <div className="border-t border-border">
            <CharacterRow index={1} name="Elena Voss" prominence="PRINCIPAL" />
            <CharacterRow index={2} name="Marcus Thane" prominence="RECURRING" />
          </div>
        </section>

        <section className="mt-14">
          <Divider label="Voice / audio player" className="mb-6" />
          <Card><CardBody>
            <AudioPlayer label="Elena — 01" duration="0:14" />
          </CardBody></Card>
        </section>

        <section className="mt-14">
          <Divider label="Manuscript progress" className="mb-6" />
          <Card><CardBody>
            <ManuscriptProgress
              chapters={SAMPLE_CHAPTERS}
              stats={{ words: 128402, chapters: 37, entities: 43 }}
            />
          </CardBody></Card>
        </section>

        <section className="mt-14">
          <Divider label="Empty & loading states" className="mb-6" />
          <div className="space-y-4">
            <EmptyState
              title="No output yet"
              description="Run a generation to see finished chapters here."
              action={<Button size="sm">Start generation</Button>}
            />
            <LoadingState label="Reading manuscript" />
          </div>
        </section>

        <section className="mt-14 mb-4">
          <Divider label="Modal & toast" className="mb-6" />
          <div className="flex gap-3">
            <Button onClick={() => setModalOpen(true)}>Edit reference</Button>
            <Button variant="secondary" onClick={() => push('Reference updated.', 'success')}>
              Fire success toast
            </Button>
            <Button variant="secondary" onClick={() => push('Could not reach backend.', 'danger')}>
              Fire error toast
            </Button>
          </div>
        </section>
      </div>

      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title="Edit reference — Elena Voss"
        footer={
          <>
            <Button variant="secondary" onClick={() => setModalOpen(false)}>Cancel</Button>
            <Button onClick={() => setModalOpen(false)}>Generate</Button>
          </>
        }
      >
        <p className="font-mono text-xs uppercase tracking-wider text-muted mb-2">Describe the transformation</p>
        <Input placeholder="Show her after the battle, injured and exhausted." />
      </Modal>
    </div>
  );
}
