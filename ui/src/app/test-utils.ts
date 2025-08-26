import { Pipe, PipeTransform } from '@angular/core';

// Mock pipes for testing
@Pipe({ name: 'speed' })
export class MockSpeedPipe implements PipeTransform {
  transform(value: any): string {
    return value ? `${value} MB/s` : '';
  }
}

@Pipe({ name: 'eta' })
export class MockEtaPipe implements PipeTransform {
  transform(value: any): string {
    return value ? `${value}s` : '';
  }
}

@Pipe({ name: 'fileSize' })
export class MockFileSizePipe implements PipeTransform {
  transform(value: any): string {
    return value ? `${value} MB` : '';
  }
}

// Mock components for testing
import { Component, Input } from '@angular/core';

@Component({
  selector: 'app-master-checkbox',
  template: '<input type="checkbox" [id]="id">'
})
export class MockMasterCheckboxComponent {
  @Input() id: string = '';
  @Input() list: any;
}

@Component({
  selector: 'app-slave-checkbox', 
  template: '<input type="checkbox" [id]="id">'
})
export class MockSlaveCheckboxComponent {
  @Input() id: string = '';
  @Input() master: any;
  @Input() checkable: any;
}