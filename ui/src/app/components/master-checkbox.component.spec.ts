import { TestBed } from '@angular/core/testing';
import { SelectAllCheckboxComponent } from './master-checkbox.component';
import { Checkable } from '../interfaces';

function makeList(ids: string[]): Map<string, Checkable> {
  const list = new Map<string, Checkable>();
  for (const id of ids) {
    list.set(id, { checked: false });
  }
  return list;
}

function makeMaster(list: Map<string, Checkable>, orderedIds: string[] | null = null) {
  const fixture = TestBed.createComponent(SelectAllCheckboxComponent);
  fixture.componentRef.setInput('id', 'queue');
  fixture.componentRef.setInput('list', list);
  if (orderedIds) {
    fixture.componentRef.setInput('orderedIds', orderedIds);
  }
  fixture.detectChanges();
  return fixture;
}

// Simulates what the item checkbox does: ngModel writes the new state, then
// the change handler reports the click to the master.
function clickItem(
  master: SelectAllCheckboxComponent,
  list: Map<string, Checkable>,
  id: string,
  shift = false,
) {
  const item = list.get(id)!;
  item.checked = !item.checked;
  master.selectionChanged(id, shift);
}

describe('SelectAllCheckboxComponent', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [SelectAllCheckboxComponent],
    }).compileComponents();
  });

  it('clicked sets checked on all list items', () => {
    const fixture = TestBed.createComponent(SelectAllCheckboxComponent);
    const list = new Map<string, Checkable>();
    list.set('u1', { checked: false });
    fixture.componentRef.setInput('id', 'queue');
    fixture.componentRef.setInput('list', list);
    fixture.componentInstance.selected = true;
    fixture.detectChanges();
    fixture.componentInstance.clicked();
    expect(list.get('u1')?.checked).toBe(true);
  });

  it('shift-click checks every item between the two clicks', () => {
    const list = makeList(['u1', 'u2', 'u3', 'u4', 'u5']);
    const master = makeMaster(list).componentInstance;

    clickItem(master, list, 'u2');
    clickItem(master, list, 'u4', true);

    expect([...list.values()].map((i) => i.checked)).toEqual([false, true, true, true, false]);
  });

  it('extends upwards as well as downwards', () => {
    const list = makeList(['u1', 'u2', 'u3', 'u4']);
    const master = makeMaster(list).componentInstance;

    clickItem(master, list, 'u4');
    clickItem(master, list, 'u2', true);

    expect([...list.values()].map((i) => i.checked)).toEqual([false, true, true, true]);
  });

  it('shift-clicking a checked box clears the range', () => {
    const list = makeList(['u1', 'u2', 'u3']);
    list.forEach((item) => (item.checked = true));
    const master = makeMaster(list).componentInstance;

    clickItem(master, list, 'u1');
    clickItem(master, list, 'u3', true);

    expect([...list.values()].map((i) => i.checked)).toEqual([false, false, false]);
  });

  it('follows the rendered order, not the map order', () => {
    // The done list renders newest-first, so its rendered order is not the
    // order the entries sit in the map. u2 lies inside the range on screen
    // and outside it in the map, which is what separates the two.
    const list = makeList(['u1', 'u2', 'u3', 'u4']);
    const master = makeMaster(list, ['u4', 'u2', 'u3', 'u1']).componentInstance;

    clickItem(master, list, 'u4');
    clickItem(master, list, 'u3', true);

    // u1 (rendered last) stays clear; u2 is swept up with the range.
    expect([...list.values()].map((i) => i.checked)).toEqual([false, true, true, true]);
  });

  it('a plain click after a range starts a new anchor', () => {
    const list = makeList(['u1', 'u2', 'u3', 'u4']);
    const master = makeMaster(list).componentInstance;

    clickItem(master, list, 'u1');
    clickItem(master, list, 'u2', true);
    clickItem(master, list, 'u4');

    expect([...list.values()].map((i) => i.checked)).toEqual([true, true, false, true]);
  });

  it('select-all clears the anchor so the next shift-click is a plain toggle', () => {
    const list = makeList(['u1', 'u2', 'u3']);
    const fixture = makeMaster(list);
    const master = fixture.componentInstance;

    clickItem(master, list, 'u1');
    master.selected = true;
    master.clicked();
    master.selected = false;
    master.clicked();
    clickItem(master, list, 'u3', true);

    expect([...list.values()].map((i) => i.checked)).toEqual([false, false, true]);
  });

  it('ignores a range whose anchor row is gone', () => {
    const list = makeList(['u1', 'u2', 'u3']);
    const master = makeMaster(list).componentInstance;

    clickItem(master, list, 'u1');
    // The anchor finishes downloading and leaves the queue.
    list.delete('u1');
    clickItem(master, list, 'u3', true);

    expect([...list.values()].map((i) => i.checked)).toEqual([false, true]);
  });
});
