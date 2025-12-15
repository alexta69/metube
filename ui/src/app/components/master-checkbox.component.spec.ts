/* eslint-disable @angular-eslint/use-component-selector */
import { render, screen } from '@testing-library/angular';
import { MasterCheckboxComponent } from './master-checkbox.component';
import { Checkable } from '../interfaces';

describe('MasterCheckboxComponent', () => {
  async function createMasterCheckboxComponent(
    override: { template?: string; componentProperties?: Record<string, unknown> } = {},
  ) { 
    override.template ||= `
<app-master-checkbox [id]="'done'" [list]="doneList" (changed)="doneSelectionChanged($event)" />
    `;

    const rendered = await render(override.template, {
      imports: [MasterCheckboxComponent],
      componentProperties: {
        doneList: new Map<string, Checkable>([
          ['url1', { checked: false }],
          ['url2', { checked: false }],
        ]),
        doneSelectionChanged: (event: Event) => { console.log(event)},
        ...override.componentProperties,
      },
    });

    return rendered;
  }

  it('should create the component', async () => {
    const { fixture } = await createMasterCheckboxComponent();
    expect(fixture.componentInstance).toBeTruthy();
    expect(screen.getByRole('checkbox')).toBeDefined();
  });
});
