/*
 *  (c) AstroPrint Product Team. 3DaGoGo, Inc. (product@astroprint.com)
 *
 *  Distributed under the GNU Affero General Public License http://www.gnu.org/licenses/agpl.html
 */

var PrintFileInfoDialog = Backbone.View.extend({
  el: '#print-file-info',
  file_list_view: null,
  template: _.template( $("#printfile-info-template").html() ),
  print_file_view: null,
  events: {
    'click .actions a.remove': 'onDeleteClicked',
    'click .actions a.print': 'onPrintClicked',
    'click .actions a.download': 'onDownloadClicked'
  },
  initialize: function(params)
  {
    this.file_list_view = params.file_list_view;
  },
  render: function()
  {
    this.$el.find('.dlg-content').html(this.template({
      p: this.print_file_view.print_file.toJSON(),
      time_format: app.utils.timeFormat
    }));
  },
  open: function(print_file_view)
  {
    this.print_file_view = print_file_view;
    this.render();
    this.$el.foundation('reveal', 'open');
  },
  onDeleteClicked: function(e)
  {
    e.preventDefault();

    var print_file = this.print_file_view.print_file;

    if (print_file) {
      var filename = print_file.get('local_filename');
      var id = print_file.get('id');
      var loadingBtn = $(e.currentTarget).closest('.loading-button');

      loadingBtn.addClass('loading');
      $.ajax({
        url: '/api/files/local/'+filename,
        type: "DELETE",
        success: _.bind(function() {
          //Update model
          if (print_file.get('local_only')) {
            this.file_list_view.file_list.remove(print_file);
          } else {
            print_file.set('local_filename', false);
            print_file.set('uploaded_on', null);
          }

          noty({text: filename+" deleted from your "+PRODUCT_NAME, type:"success", timeout: 3000});
          this.print_file_view.render();
          this.$el.foundation('reveal', 'close');
        }, this),
        error: function() {
          noty({text: "Error deleting "+filename, timeout: 3000});
        },
        always: function() {
          loadingBtn.removeClass('loading');
        }
      });
    }
  },
  onPrintClicked: function(e)
  {
    this.print_file_view.printClicked(e);
    this.$el.foundation('reveal', 'close');
  },
  onDownloadClicked: function(e)
  {
    this.print_file_view.downloadClicked(e);
    this.$el.foundation('reveal', 'close');
  }
});

var FileUploadFiles = FileUploadCombined.extend({
  progressBar: null,
  buttonContainer: null,
  initialize: function(options)
  {
    this.progressBar = options.progressBar;
    this.buttonContainer = options.buttonContainer;

    FileUploadCombined.prototype.initialize.call(this, options);
  },
  started: function(data)
  {
    if (data.files && data.files.length > 0) {
      this.buttonContainer.hide();
      this.progressBar.show();
      FileUploadCombined.prototype.started.call(this, data);
    }
  },
  progress: function(progress, message)
  {
    var intPercent = Math.round(progress);

    this.progressBar.find('.meter').css('width', intPercent+'%');
    if (!message) {
      message = "Uploading ("+intPercent+"%)";
    }
    this.progressBar.find('.progress-message span').text(message);
  },
  onError: function(type, error)
  {
    var message = error;

    switch(error) {
      //case 'invalid_data':
      //case 'http_error_400':
      //break;

      case 'http_error_401':
        message = 'An AstroPrint account is needed to upload designs';
        $('#login-modal').foundation('reveal', 'open');
      break;

      case null:
        message = 'There was an error uploading your file';
      break;
    }

    noty({text: message, timeout: 3000});
    this.resetUploadArea();
    console.error(error);
  },
  onPrintFileUploaded: function()
  {
    this.resetUploadArea();
  },
  resetUploadArea: function()
  {
    this.progressBar.hide();
    this.buttonContainer.show();
    this.progress(0);
  }
});

var UploadView = Backbone.View.extend({
  uploadBtn: null,
  progressBar: null,
  buttonContainer: null,
  initialize: function(options)
  {
    this.progressBar = this.$('.upload-progress');
    this.buttonContainer = this.$('.upload-buttons');

    this.uploadBtn = new FileUploadFiles({
      el: "#files-view .file-upload-view .file-upload",
      progressBar: this.$('.upload-progress'),
      buttonContainer: this.$('.file-upload-button'),
      dropZone: options.dropZone
    });

    this.render();
  },
  render: function()
  {
    var buttonContainer = this.$('.file-upload-button');

    if (app.printerProfile.get('driver') == 's3g') {
      buttonContainer.find('.extensions').text('stl, x3g');
      buttonContainer.find('input').attr('accept', '.stl, .x3g');
    } else {
      buttonContainer.find('.extensions').text('stl, gcode');
      buttonContainer.find('input').attr('accept', '.stl, .gcode, .gco');
    }

    this.uploadBtn.refreshAccept();
  }
});

var PrintFileView = Backbone.View.extend({
  template: _.template( $("#print-file-template").html() ),
  print_file: null,
  list: null,
  printWhenDownloaded: false,
  downloadProgress: null,
  initialize: function(options)
  {
    this.list = options.list;
    this.print_file = options.print_file;
  },
  slideName: function () {
    if (!this.$(".div-container").size() || this.$(".div-container").width()<=0) {
      setTimeout(_.bind(this.slideName,this), 500); // give everything some time to render
    } else {
      if(this.$('.text').width() >= this.$('.div-container').width()){
        this.$('.text').addClass('slide-text')
      } else {
        this.$('.text').removeClass('slide-text')
      }
    }
  },
  render: function()
  {
    var print_file = this.print_file.toJSON();

    if (print_file.local_filename) {
      this.$el.removeClass('remote');
    } else {
      this.$el.addClass('remote');
    }

    if (print_file.printFileName) {
      print_file.name = print_file.printFileName;
    }

    this.$el.empty();
    this.downloadProgress = null;
    this.$el.html(this.template({
      p: print_file,
      time_format: app.utils.timeFormat,
      size_format: app.utils.sizeFormat
    }));

    this.delegateEvents({
      'click .left-section, .middle-section': 'infoClicked',
      'click a.print': 'printClicked',
      'click a.download': 'downloadClicked',
      'click a.dw-cancel': 'cancelDownloadClicked'
    });

    this.slideName();
  },
  infoClicked: function(evt)
  {
    if (evt) evt.preventDefault();

    this.list.info_dialog.open(this);
  },
  downloadClicked: function(evt)
  {
    if (evt) evt.preventDefault();

    $.getJSON('/api/astroprint/print-files/'+this.print_file.get('id')+'/download')
      .fail(function(){
        noty({text: "There was an error starting the download.", timeout: 3000});
      });
  },
  cancelDownloadClicked: function(evt)
  {
    evt.preventDefault();

    $.ajax({
      url: '/api/astroprint/print-files/'+this.print_file.get('id')+'/download',
      method: 'DELETE'
    })
      .fail(function() {
        noty({text: "Unable to cancel download.", timeout: 3000});
      });
  },
  printClicked: function (evt)
  {
    if (evt) evt.preventDefault();

    var filename = this.print_file.get('local_filename');

    if (filename) {
      //We can't use evt because this can come from another source than the row print button
      var loadingBtn = this.$('.loading-button.print');

      loadingBtn.addClass('loading');
      $.ajax({
          url: '/api/files/local/'+filename,
          type: "POST",
          dataType: "json",
          contentType: "application/json; charset=UTF-8",
          data: JSON.stringify({command: "select", print: true})
      })
      .done(_.bind(function() {
        setTimeout(function(){
          loadingBtn.removeClass('loading');
        },2000);
      }, this))
      .fail(function(xhr) {
        var error = null;
        if (xhr.status == 409) {
          error = xhr.responseText;
        }
        noty({text: error ? error : "There was an error starting the print", timeout: 3000});
        loadingBtn.removeClass('loading');
      })
    } else {
      //We need to download and print
      this.printWhenDownloaded = true;
      this.downloadClicked();
    }
  }
});

var StorageControlView = Backbone.View.extend({
  print_file_view: null,
  events: {
    'click a.USB': 'usbClicked',
    'click a.local': 'localClicked',
    'click a.cloud': 'cloudClicked'
  },
  selected: null,
  exploringLocation: null,
  initialize: function(options)
  {
    this.print_file_view = options.print_file_view;
    //cloud default selection
    this.$('a.active').removeClass('active');
    this.$('a.cloud').addClass('active');
    this.selected = 'cloud';
  },
  _cleanUrlNavigation: function(location){
    return location.replace(/\/+/g, "/");
  },
  composeLocation: function(locationNavigation){
    if(locationNavigation != 'back'){
      if(this.exploringLocation != '/'){
        this.exploringLocation = this._cleanUrlNavigation(locationNavigation);
      } else {
        this.exploringLocation = this._cleanUrlNavigation(this.exploringLocation + locationNavigation);
      }
    } else {
      if(!this.print_file_view.usbfile_list.topLocationMatched(this.exploringLocation)){//BACK
        var spl = this._cleanUrlNavigation(this.exploringLocation).split('/');
        spl.splice(-1,1);
        this.exploringLocation = this._cleanUrlNavigation('/'+(spl).join('/'));
      } else {//TOP LOCATION
        this.exploringLocation = '/';
      }
    }
  },
  selectStorage: function(storage)
  {
    this.$('a.active').removeClass('active');
    this.$('a.'+storage).addClass('active');
    this.selected = storage;
    this.print_file_view.render();
  },
  usbClicked: function(e)
  {
    e.preventDefault();
    $('h3.printablefiles-message').addClass('hide');
    this.exploringLocation = '/';
    this.selectStorage('USB');
  },
  localClicked: function(e)
  {
    e.preventDefault();
    $('h3.printablefiles-message').removeClass('hide');
    this.selectStorage('local');
  },
  cloudClicked: function(e)
  {
    e.preventDefault();
    $('h3.printablefiles-message').removeClass('hide');

    if (LOGGED_USER) {
      this.selectStorage('cloud');
    } else {
      $('#login-modal').foundation('reveal', 'open');
    }
  }
});

var PrintFilesListView = Backbone.View.extend({
  info_dialog: null,
  print_file_views: [],
  usb_file_views: [],
  storage_control_view: null,
  file_list: null,
  usbfile_list: null,
  refresh_threshold: 1000, //don't allow refreshes faster than this (in ms)
  last_refresh: 0,
  refreshing: false,
  need_to_be_refreshed: false,
  storageLocation: null,
  events: {
    'click .list-header button.sync': 'forceSync'
  },
  initialize: function(options) {
    this.file_list = new PrintFileCollection();
    this.usbfile_list = new USBFileCollection();
    this.info_dialog = new PrintFileInfoDialog({file_list_view: this});
    this.storage_control_view = new StorageControlView({
      el: this.$('.list-header ul.storage'),
      print_file_view: this
    });

    app.eventManager.on('astrobox:cloudDownloadEvent', this.downloadProgress, this);
    app.eventManager.on('astrobox:MetadataAnalysisFinished', _.bind(this.onMetadataAnalysisFinished, this));
    this.listenTo(this.file_list, 'remove', this.onFileRemoved);
    app.eventManager.on('astrobox:externalDrivePlugged', this.externalDrivesRefresh, this);
    app.eventManager.on('astrobox:externalDriveEjected', this.externalDrivesRefresh, this);
    app.eventManager.on('astrobox:externalDrivePhisicallyRemoved', this.externalDrivesRefresh, this);

    $.getJSON('/api/files/storage-location')
      .success(_.bind(function(data){
        this.storageLocation = data;
        this.refresh('local', options.syncCompleted);
      },this))
      .fail(function(error){
        console.error();
        this.refresh('local', options.syncCompleted);
      }
    );

  },
  externalDrivesRefresh: function(){

    var selectedStorage = this.storage_control_view.selected;

    if(selectedStorage && selectedStorage == 'USB'){
      this.render();
    }
  },
  render: function()
  {
    var list = this.$('.design-list-container');
    var selectedStorage = this.storage_control_view.selected;

    if(selectedStorage && selectedStorage == 'USB'){//CLICK IN USB TAB

      this.$('.loading-button.sync').addClass('loading');

      var location = this.storage_control_view.exploringLocation;

      //CLEAN FILE LIST SHOWED

      list.children().detach();

      //FETCH USB FILES

      this.usb_file_views = [];
      this.usbfile_list.syncLocation(location)
        .done(_.bind(function(data){

          if(location != '/'){
            var backView = new BackFolderView(
              {
                parentView: this
              });
              backView.render();
            this.usb_file_views.push(backView);
            list.append(backView.$el);
          }

          if(this.storageLocation){
            this.usbfile_list.each(_.bind(function(file, idx) {
              if(this.usbfile_list.extensionMatched(file.get('name'))){
                var usb_file_view = new USBFileView(file,this);
              } else {

                var usb_file_view = new BrowsingFileView(
                  {
                    parentView: this,
                    file: file
                  });
                usb_file_view.render();
                this.usb_file_views.push( usb_file_view );
              }
              usb_file_view.render();
              this.usb_file_views.push( usb_file_view );
            }, this));
          } else {
            noty({text: "There was an error retrieving external storage location", timeout: 3000});
          }

          if (this.usb_file_views.length) {
            _.each(this.usb_file_views, function(p) {
              list.append(p.$el);
            });

            this.$('.loading-button.sync').removeClass('loading');

          } else {
            list.html(
              '<div class="empty panel radius" align="center">'+
              ' <i class="icon-inbox empty-icon"></i>'+
              ' <h3>Nothing here yet.</h3>'+
              '</div>'
            );
            this.$('.loading-button.sync').removeClass('loading');
          }

        },this))
        .fail(function(){
          noty({text: "There was an error retrieving files in the drive", timeout: 3000});
        });

    } else {

      list.children().detach();

      if (selectedStorage) {
        if(this.need_to_be_refreshed && selectedStorage == 'local'){
          this.refresh('local');
          this.need_to_be_refreshed = false;
        } else {
          var filteredViews = _.filter(this.print_file_views, function(p){
            if (selectedStorage == 'local') {
              if (p.print_file.get('local_filename')) {
                return true
              }
            } else if (!p.print_file.get('local_only')) {
              return true;
            }

            return false;
          });
        }
      } else {
        var filteredViews = this.print_file_views;
      }

      if (filteredViews && filteredViews.length) {
        _.each(filteredViews, function(p) {
          list.append(p.$el);
        });
      } else {
        list.html(
          '<div class="empty panel radius" align="center">'+
          ' <i class="icon-inbox empty-icon"></i>'+
          ' <h3>Nothing here yet.</h3>'+
          '</div>'
        );
      }
    }
  },
  refresh: function(kindOfSync, doneCb)
  {
    if(this.storage_control_view.selected == 'USB'){

      this.storage_control_view.selectStorage('USB');

    } else {

      var now = new Date().getTime();

      if (this.last_refresh == 0 || this.last_refresh < (now - this.refresh_threshold) ) {
        this.last_refresh = now;

        if ( !this.refreshing ) {
          this.refreshing = true;

          switch(kindOfSync){
            case 'cloud':
              var loadingArea = this.$('.loading-button.sync');
              var syncPromise = this.file_list.syncCloud();
            break;

            case 'local':
              var loadingArea = this.$('.local-loading');
              var syncPromise = this.file_list.fetch();
            break;

          }

          loadingArea.addClass('loading');
          syncPromise
            .done(_.bind(function(){
              this.print_file_views = [];
              this.file_list.each(_.bind(function(print_file, idx) {
                var print_file_view = new PrintFileView({
                  list: this,
                  print_file: print_file,
                  attributes: {'class': 'row'}
                });
                print_file_view.render();
                this.print_file_views.push( print_file_view );
              }, this));

              this.$('.design-list-container').empty();
              this.render();

              if (_.isFunction(doneCb)) {
                doneCb(true);
              }

              $.localtime.format(this.$el);

              loadingArea.removeClass('loading');
              this.refreshing = false;
            }, this))
            .fail(_.bind(function(){
              noty({text: "There was an error retrieving print files", timeout: 3000});

              if (_.isFunction(doneCb)) {
                doneCb(false);
              }

              loadingArea.removeClass('loading');
              this.refreshing = false;
            }, this));
        }
      }
    }
  },
  downloadProgress: function(data)
  {
    var print_file_view = _.find(this.print_file_views, function(v) {
      return v.print_file.get('id') == data.id;
    });

    if (print_file_view) {
      var progressContainer = print_file_view.$('.print-file-options');

      switch (data.type) {
        case 'progress':
        {
          if (!progressContainer.hasClass('downloading')) {
            progressContainer.addClass('downloading');
          }

          if (!print_file_view.downloadProgress) {
            var progress = progressContainer.find('.download-progress');

            print_file_view.downloadProgress = progress.circleProgress({
              value: 0,
              animation: false,
              size: progressContainer.innerWidth(),
              fill: { color: 'black' }
            });
          } else {
            print_file_view.downloadProgress.circleProgress({value: data.progress / 100.0});
          }

          var label = print_file_view.$('.download-progress span');

          label.html(Math.floor(data.progress) + '<i>%</i>');
        }
        break;

        case 'success':
        {
          var print_file = print_file_view.print_file;

          if (print_file) {
            print_file.set('local_filename', data.filename);
            print_file.set('print_time', data.print_time);
            print_file.set('layer_count', data.layer_count);
            print_file.set('uploaded_on', Date.now() / 1000);

            print_file_view.render();
            $.localtime.format(print_file_view.$el);

            if (print_file_view.printWhenDownloaded) {
              print_file_view.printWhenDownloaded = false;
              print_file_view.printClicked();
            }
          }
        }
        break;

        case 'error':
        {
          progressContainer.removeClass('downloading').addClass('failed');
          console.error('Error downloading file: '+data.reason);
          setTimeout(function(){
            progressContainer.removeClass('failed');
          },3000);
        }
        break;

        case 'cancelled':
        {
          progressContainer.removeClass('downloading');
        }
        break;
      }
    }
  },
  forceSync: function()
  {
    this.refresh('cloud');
  },
  onFileRemoved: function(print_file)
  {
    //Find the view that correspond to this print file
    var view = _.find(this.print_file_views, function(v) {
      return v.print_file == print_file;
    });

    if (view) {
      //Remove from DOM
      view.remove();

      //Remove from views array
      this.print_file_views.splice(this.print_file_views.indexOf(view), 1);
    }
  },
  onMetadataAnalysisFinished: function(data)
  {
    var affected_view = _.find(this.print_file_views, function(v){
      return v.print_file.get('name') == data.file;
    });

    if (affected_view) {
      affected_view.print_file.set('info', data.result);
      affected_view.render();
    }
  }
});

var FilesView = Backbone.View.extend({
  el: '#files-view',
  uploadView: null,
  printFilesListView: null,
  events: {
    'show': 'onShow'
  },
  initialize: function(options)
  {
    this.uploadView = new UploadView({
      el: this.$el.find('.file-upload-view'),
      dropZone: this.$el
    });
    this.printFilesListView = new PrintFilesListView({
      el: this.$el.find('.design-list'),
      forceSync: options.forceSync,
      syncCompleted: options.syncCompleted
    });

    this.listenTo(app.printerProfile, 'change:driver', this.onDriverChanged);
  },
  refreshPrintFiles: function()
  {
    var promise = $.Deferred();
    this.printFilesListView.refresh('cloud', function(success) {
      if (success) {
        promise.resolve();
      } else {
        promise.reject('unable_to_refresh');
      }
    });

    return promise;
  },
  fileInfo: function(fileId)
  {
    var view = _.find(this.printFilesListView.print_file_views, function(v) {
      return v.print_file.get('id') == fileId;
    });

    this.printFilesListView.storage_control_view.selectStorage('cloud');
    this.showFileInfoView(view);
  },
  fileInfoByName: function(name)
  {
    var view = _.find(this.printFilesListView.print_file_views, function(v) {
      return v.print_file.get('name') == name;
    });

    this.showFileInfoView(view);
  },
  showFileInfoView: function(view)
  {
    if (view) {
      view.infoClicked();
    }
  },
  onShow: function()
  {
    this.printFilesListView.refresh('local');
  },
  onDriverChanged: function()
  {
    this.uploadView.render();
    this.printFilesListView.refresh('cloud');
  }
});

var ReplaceFileDialog = Backbone.View.extend({
  el: '#local-file-exists-dlg',
  filename: null,
  usbFileView: null,
  copyFinishedPromise: null,
  template: _.template( $("#local-file-exists-template").html() ),
  events: {
    'click button.replace': 'onReplaceClicked',
    'click button.cancel': 'onCancelClicked',
    'closed.fndtn.reveal': 'onClose'
  },
  initialize: function(params)
  {
    this.filename = params.filename;
    this.usbFileView = params.usbFileView;
    this.copyFinishedPromise = params.copyFinishedPromise;
  },
  render: function()
  {
    this.$el.find('.dlg-content').html(this.template({
      filename: this.filename
    }));
  },
  open: function(print_file_view)
  {
    this.render();
    this.$el.foundation('reveal', 'open');
  },
  onReplaceClicked: function(e)
  {
    if(e) e.preventDefault();

    this.$el.foundation('reveal', 'close');
    this.usbFileView.copyFile(this.copyFinishedPromise);
  },
  onCancelClicked: function(e)
  {
    if(e) e.preventDefault();

    this.$el.foundation('reveal', 'close');
    this.copyFinishedPromise.reject();
  },
  onClose: function(){
    this.usbFileView.$('button.copy').removeClass('hide')
    this.usbFileView.$('button.print').removeClass('hide')
  }
});

var USBFileView = Backbone.View.extend({
  template: _.template( $("#usb-file-template").html() ),
  usb_file: null,
  copying: null,
  progress: -1,
  localFileExistsDialog: null,
  ejectBeforePrintDialog: null,
  parentView: false,
  initialize: function(file,parentView)
  {
    this.usb_file = file;
    this.parentView = parentView;

  },
  render: function()
  {
    var usb_file = this.usb_file.toJSON();

    this.$el.empty();
    //this.downloadProgress = null;
    this.$el.html(this.template({
      p: this.usb_file.get('name').split('/').splice(-1,1)[0]
    }));

    this.delegateEvents({
      'click button.copy': 'copyClicked',
      'click button.print': 'printClicked'
    });

    this.slideName();
  },
  slideName: function () {
    if (!this.$(".div-container").size() || this.$(".div-container").width()<=0) {
      setTimeout(_.bind(this.slideName,this), 500); // give everything some time to render
    } else {
      if(this.$('.text').width() >= this.$('.div-container').width()){
        this.$('.text').addClass('slide-text')
      } else {
        this.$('.text').removeClass('slide-text')
      }
    }
  },
  _print: function(){

    var filename = this.usb_file.get('name').split('/').splice(-1,1)[0];

    //We can't use evt because this can come from another source than the row print button
    var loadingBtn = this.$('.loading-button.print');

    loadingBtn.addClass('loading');
    $.ajax({
        url: '/api/files/local/'+filename,
        type: "POST",
        dataType: "json",
        contentType: "application/json; charset=UTF-8",
        data: JSON.stringify({command: "select", print: true})
    })
    .done(_.bind(function() {
      setTimeout(function(){
        loadingBtn.removeClass('loading');
      },2000);
    }, this))
    .fail(function(xhr) {
      var error = null;
      if (xhr.status == 409) {
        error = xhr.responseText;
      }
      noty({text: error ? error : "There was an error starting the print", timeout: 3000});
      loadingBtn.removeClass('loading');
    })
  },
  printClicked: function(evt){

    if (evt) evt.preventDefault();

    this.tryToCopyFile()
      .done(_.bind(function(){

        var EjectBeforePrintDialog = Backbone.View.extend({
          el: '#eject-before-print-dlg',
          drive: null,
          parentView: null,
          template: _.template( $("#eject-before-print-template").html() ),
          events: {
            'click button.eject-no': 'onNoClicked',
            'click button.eject-yes': 'onYesClicked'
          },
          initialize: function(params)
          {
            this.drive = params.drive;
            this.parentView = params.parentView;
          },
          render: function()
          {
            this.$el.find('.dlg-content').html(this.template({
              filename: this.filename
            }));
          },
          open: function(print_file_view)
          {
            this.render();
            this.$el.foundation('reveal', 'open');
          },
          onYesClicked: function(e)
          {
            if(e) e.preventDefault();

            this.$el.foundation('reveal', 'close');

            $.ajax({
                url: '/api/files/eject',
                type: "POST",
                dataType: "json",
                data:
                  {
                    drive: this.drive
                  }
            })
            .done(_.bind(function(data) {
              if(data.error){
                var error = data.error
                noty({text: "There was an error ejecting drive" + (error ? ': ' + error : ""), timeout: 3000});
              } else {
                noty({text: "Drive ejected successfully. You can remove the external drive", type: 'success', timeout: 3000});
                this.parentView.$('button.copy').removeClass('hide')
                this.parentView.$('button.print').removeClass('hide')
                this.parentView._print();
              }
              setTimeout(_.bind(function(){
                loadingBtn.removeClass('loading');
              },this),2000);
            }, this))
            .fail(function(xhr) {
              var error = xhr.responseText;
              noty({text: error ? error : "There was an error ejecting drive", timeout: 3000});
              this.parentView.$('button.copy').removeClass('hide')
              this.parentView.$('button.print').removeClass('hide')
              loadingBtn.removeClass('loading');
            })
            this.$el.foundation('reveal', 'close');
          },
          onNoClicked: function(e)
          {
            if(e) e.preventDefault();

            this.$el.foundation('reveal', 'close');

            this.parentView.$('button.copy').removeClass('hide')
            this.parentView.$('button.print').removeClass('hide')

            this.parentView._print();
          }
        });

        this.ejectBeforePrintDialog = new EjectBeforePrintDialog(
          {
            drive: this.usb_file.get('name').split('/').slice(0, -1).join('/'),
            parentView: this
          }
        );
        this.ejectBeforePrintDialog.open();

      },this))
      .fail(function(){
        noty({text: "Print can not be starterd. Try it again later", timeout: 3000});
      });
  },
  copyToHomeProgressUpdater: function(data){
    this.progress = data.progress

    this.$('.loading-content').html(_.template( $("#copy-to-home-progress").html() )({
      progress: this.progress
    }));
  },
  copyClicked: function (evt)
  {
    if (evt) evt.preventDefault();

    this.$('button.copy').addClass('hide')
    this.$('button.print').addClass('hide')

    this.tryToCopyFile()
      .done(_.bind(function(){
        this.$('button.copy').removeClass('hide')
        this.$('button.print').removeClass('hide')
      },this))
      .fail(_.bind(function(){
        this.$('button.copy').removeClass('hide')
        this.$('button.print').removeClass('hide')
      },this));
  },
  copyFile: function(promise){

    var filename = this.usb_file.get('name');

    app.eventManager.on('astrobox:copyToHomeProgress', this.copyToHomeProgressUpdater, this);

    var loadingBtn = this.$('.loading-button.print');

    loadingBtn.addClass('loading');

    $.ajax({
        url: '/api/files/copy-to-local',
        type: "POST",
        dataType: "json",
        data:
          {
            file: filename,
            observerId: AP_SESSION_ID
          }
    })
    .done(_.bind(function(data) {
      this.$('.loading-content').html("");
      if(!data.response){
        var error = data.error
        noty({text: "There was an error copying file...Try it again later", timeout: 3000});
        promise.reject();
      } else {
        loadingBtn.removeClass('loading');
        noty({text: "File " + filename + " copied to home",type: 'success',timeout: 3000});
        this.parentView.need_to_be_refreshed = true;
        promise.resolve();
      }
      loadingBtn.removeClass('loading');
      this.$('button.copy').removeClass('hide')
      this.$('button.print').removeClass('hide')
      app.eventManager.off('astrobox:copyToHomeProgress', this.copyToHomeProgressUpdater, this);
      this.$('.loading-content').html('');
      this.$el.foundation('reveal', 'close');
    }, this))
    .fail(_.bind(function(xhr) {
      this.$('.loading-content').html("");
      var error = data.error
      loadingBtn.removeClass('loading');
      noty({text: "There was an error copying file...Try it again later", timeout: 3000});
      setTimeout(_.bind(function(){
        loadingBtn.removeClass('loading');
      },this),2000);
      this.$el.foundation('reveal', 'close');
      this.$('button.copy').removeClass('hide')
      this.$('button.print').removeClass('hide')
      app.eventManager.off('astrobox:copyToHomeProgress', this.copyToHomeProgressUpdater, this);
      this.$('.loading-content').html('');
      promise.rejct();
    },this));
  },
  tryToCopyFile: function(){

    var promise = $.Deferred();

    var filename = this.usb_file.get('name').split('/').splice(-1,1)[0];

    $.getJSON('/api/files/local-file-exists/' + filename)
      .success(_.bind(function(data){
        if(data.response){

          this.localFileExistsDialog = new ReplaceFileDialog(
            {
              filename: filename,
              copyFinishedPromise: promise,
              usbFileView: this
            }
          );
          this.localFileExistsDialog.open();

        } else {
          this.copyFile(promise);
        }
      },this))
      .fail(function(){
        noty({text: "There was an error copying selecte file. Try it again later.", timeout: 3000});
        this.$('button.copy').removeClass('hide')
        this.$('button.print').removeClass('hide')
      });

    return promise;
  }
});

var BrowsingFileView = Backbone.View.extend({
  template: _.template( $("#browsing-file-template").html() ),
  file: null,
  parentView: null,
  initialize: function(data)
  {
    this.parentView = data.parentView;

    data.file.set('location',data.file.get('name'));

    if(this.parentView.storage_control_view.exploringLocation != '/'){
      data.file.set('name',data.file.get('name').split(this.parentView.storage_control_view.exploringLocation)[1].replace('/',''));
    } else {
      data.file.set('name',data.file.get('name').split(this.parentView.storageLocation)[1].replace('/',''))
    }

    this.file = data.file;
  },
  slideName: function () {
    if (!this.$(".div-container").size() || this.$(".div-container").width()<=0) {
      setTimeout(_.bind(this.slideName,this), 500); // give everything some time to render
    } else {
      if(this.$('.text').width() >= this.$('.div-container').width()){
        this.$('.text').addClass('slide-text')
      } else {
        this.$('.text').removeClass('slide-text')
      }
    }
  },
  render: function()
  {
    var print_file = this.file.toJSON();

    this.$el.empty();
    this.downloadProgress = null;
    this.$el.html(this.template({
      p: print_file
    }));

    this.delegateEvents({
      'click div.exploreFolder': 'exploreFolder',
      'click button.eject': 'eject'
    });

    this.slideName();
  },
  eject: function(evt){
    if (evt) evt.preventDefault();

    this.$('button.eject').addClass('hide');
    this.$('.loading-button.eject').addClass('loading');

    $.ajax({
        url: '/api/files/eject',
        type: "POST",
        dataType: "json",
        data:
          {
            drive: this.file.get('name')
          }
    })
    .done(_.bind(function(data) {
      if(data.error){
        var error = data.error
        noty({text: "There was an error ejecting drive" + (error ? ': ' + error : ""), timeout: 3000});
        this.$('button.eject').removeClass('hide');
      } else {
        this.$('.loading-button.eject').removeClass('loading');
        noty({text: "Drive ejected successfully. You can remove the external drive", type: 'success', timeout: 3000});
        this.parentView.render()
      }
    }, this))
    .fail(function(xhr) {
      var error = xhr.responseText;
      noty({text: error ? error : "There was an error ejecting drive", timeout: 3000});
      this.$('.loading-button.eject').removeClass('loading');
      this.$('button.eject').removeClass('hide');
      this.parentView.refresh()
    })
  },
  exploreFolder: function (evt)
  {
    if (evt) evt.preventDefault();

    var filename = this.file.get('location');

    var loadingBtn = this.$('.loading-button.print');

    loadingBtn.addClass('loading');

    this.parentView.storage_control_view.selected = 'USB';
    this.parentView.storage_control_view.composeLocation(filename);
    this.parentView.render();

  }
});

var BackFolderView = BrowsingFileView.extend({
  template: _.template( $("#back-folder-template").html() ),
  initialize: function(data)
  {
    this.parentView = data.parentView;
  },
  render: function()
  {
    var print_file = {
      name: 'back',
      icon: 'folder'
    }

    this.$el.empty();
    this.downloadProgress = null;
    this.$el.html(this.template({
      p: print_file
    }));

    this.delegateEvents({
      'click div.exploreFolder': 'exploreFolder'
    });
  },
  exploreFolder: function (evt)
  {
    if (evt) evt.preventDefault();

    var filename = 'back'

    var loadingBtn = this.$('.loading-button.print');

    loadingBtn.addClass('loading');

    this.parentView.storage_control_view.selected = 'USB';
    this.parentView.storage_control_view.composeLocation(filename);
    this.parentView.render();

  }
});
