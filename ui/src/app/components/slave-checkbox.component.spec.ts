import { TestBed } from '@angular/core/testing';
import { SelectAllCheckboxComponent } from './master-checkbox.component';
import { ItemCheckboxComponent } from './slave-checkbox.component';

describe('ItemCheckboxComponent', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ItemCheckboxComponent, SelectAllCheckboxComponent],
    }).compileComponents();
  });

  it('creates with master and checkable inputs', () => {
    const masterFixture = TestBed.createComponent(SelectAllCheckboxComponent);
    masterFixture.componentRef.setInput('id', 'q');
    masterFixture.componentRef.setInput('list', new Map());
    masterFixture.detectChanges();

    const itemFixture = TestBed.createComponent(ItemCheckboxComponent);
    itemFixture.componentRef.setInput('id', 'row1');
    itemFixture.componentRef.setInput('master', masterFixture.componentInstance);
    itemFixture.componentRef.setInput('checkable', { checked: false });
    itemFixture.detectChanges();
    expect(itemFixture.componentInstance).toBeTruthy();
  });
});
