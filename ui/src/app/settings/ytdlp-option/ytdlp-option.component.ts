import { Component, OnInit } from '@angular/core';
import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { faSave } from '@fortawesome/free-solid-svg-icons';

@Component({
  selector: 'app-ytdlp-option',
  templateUrl: './ytdlp-option.component.html',
  styleUrls: ['./ytdlp-option.component.sass'],
  standalone: false
})

export class YtdlpOptionComponent implements OnInit {
  faSave = faSave;
  ytdlpOptions: string = '';
  isSuccess: boolean = true;
  isSaving: boolean = false;
  msg: string = '';

  constructor(private http: HttpClient) {}

  ngOnInit(): void {
    this.loadOptions();
  }
  async loadOptions(): Promise<void> {
    this.msg = '';

    try {
      const data = await firstValueFrom(this.http.get('ytdl_options'));
      this.ytdlpOptions =  JSON.stringify(data, null, 2);
    } catch (error) {
      this.msg = 'Failed to load options.';
      alert(`Error loading yt-dlp options: ${error.message}`);
      this.isSuccess=false;
    }
  }
  async saveOptions(): Promise<void> {
    this.isSaving = true;
    this.isSuccess=true;
    this.msg = '';
    if (!this.ytdlpOptions) {
      this.ytdlpOptions='{}';
    }

    try {
      const payload = JSON.parse(this.ytdlpOptions);
      const data = await firstValueFrom(this.http.post('ytdl_options', payload));
      this.msg = data['msg'];
    } catch (error) {
      if (error instanceof SyntaxError) {
        this.msg = 'Invalid JSON format. Please check your input.';
      } else {
        this.msg = 'Failed to save options.';
        alert(`Error saving yt-dlp options: ${error.message}`);
      }
      this.isSuccess=false;
    } finally {
      this.isSaving = false;
    }
  }
}