Procedure ExportSchematic;
Var
    Inputs, Status : TStringList;
    SourcePath, TargetPath, Entry : String;
    I, Sep : Integer;
    ServerDoc : IServerDocument;
    Doc : ISch_Document;
    Picture : TMetafile;
    Canvas : TMetafileCanvas;
Begin
    Inputs := TStringList.Create;
    Status := TStringList.Create;
    Inputs.LoadFromFile('__INPUTS__');
    For I := 0 To Inputs.Count - 1 Do
    Begin
        Entry := Inputs.Strings(I);
        Sep := Pos('|', Entry);
        SourcePath := Copy(Entry, 1, Sep-1);
        TargetPath := Copy(Entry, Sep+1, Length(Entry));
        ServerDoc := Client.OpenDocument('SCH', SourcePath);
        If ServerDoc = Nil Then Exit;
        Client.ShowDocument(ServerDoc);
        Doc := SchServer.GetSchDocumentByPath(SourcePath);
        If Doc = Nil Then Exit;
        Picture := TMetafile.Create;
        Picture.Enhanced := True;
        Picture.Width := 6000;
        Picture.Height := 4000;
        Canvas := TMetafileCanvas.Create(Picture, 0);
        Doc.RedrawToDC(Canvas.Handle, 0, 1);
        Canvas.Free;
        Picture.SaveToFile(TargetPath);
        Picture.Free;
        Status.Add('Exported=' + IntToStr(I));
        Status.SaveToFile('__STATUS__');
        Client.CloseDocument(ServerDoc);
    End;
    Status.Add('Complete');
    Status.SaveToFile('__STATUS__');
    Status.Free;
    Inputs.Free;
End;
