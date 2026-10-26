Procedure VerifyProject;
Var
    Workspace : IWorkspace;
    Project : IProject;
    Violation : IViolation;
    Messages : IMessagesManager;
    Item : IMessageItem;
    Inputs, Lines, NetLines : TStringList;
    Requested, LevelText : String;
    I, J, K, L : Integer;
    Ok : Boolean;
    ServerDoc : IServerDocument;
    NativeDoc : IDocument;
    Net : INet;
    NetPin : INetItem;
    Cancelled : LongBool;
    Found : Boolean;
Begin
    Inputs := TStringList.Create;
    Inputs.LoadFromFile('__INPUTS__');
    Requested := Inputs.Strings(0);
    Workspace := GetWorkspace;
    Workspace.DM_OpenProject(Requested, True);
    Found := False;
    For I := 0 To Workspace.DM_ProjectCount - 1 Do
    Begin
        Project := Workspace.DM_Projects(I);
        If UpperCase(Project.DM_ProjectFullPath) = UpperCase(Requested) Then
        Begin
            Found := True;
            Lines := TStringList.Create;
            Lines.Add('Project=' + Project.DM_ProjectFullPath);
            For J := 1 To Inputs.Count - 1 Do
            Begin
                ServerDoc := Client.OpenDocument('SCH', Inputs.Strings(J));
                If ServerDoc <> Nil Then Client.ShowDocument(ServerDoc);
            End;
            Project.DM_SetAsCurrentProject;
            Cancelled := False;
            Ok := Project.DM_CompileEx(True, Cancelled);
            Lines.Add('LogicalDocumentCount=' + IntToStr(Project.DM_LogicalDocumentCount));
            NetLines := TStringList.Create;
            For J := 0 To Project.DM_LogicalDocumentCount - 1 Do
            Begin
                NativeDoc := Project.DM_LogicalDocuments(J);
                Lines.Add('Document=' + NativeDoc.DM_FullPath);
                Lines.Add('ComponentCount=' + IntToStr(NativeDoc.DM_ComponentCount));
                Lines.Add('NetCount=' + IntToStr(NativeDoc.DM_NetCount));
                For K := 0 To NativeDoc.DM_NetCount - 1 Do
                Begin
                    Net := NativeDoc.DM_Nets(K);
                    For L := 0 To Net.DM_PinCount - 1 Do
                    Begin
                        NetPin := Net.DM_Pins(L);
                        NetLines.Add(Net.DM_NetName + '|' + NetPin.DM_PhysicalPartDesignator + '|' + NetPin.DM_PinNumber);
                    End;
                End;
            End;
            NetLines.SaveToFile('__NETS__');
            NetLines.Free;
            For J := 0 To Project.DM_ViolationCount - 1 Do
            Begin
                Violation := Project.DM_Violations(J);
                LevelText := '[Other]';
                If Violation.DM_ErrorLevel = eErrorLevelWarning Then LevelText := '[Warning]';
                If Violation.DM_ErrorLevel = eErrorLevelError Then LevelText := '[Error]';
                If Violation.DM_ErrorLevel = eErrorLevelFatal Then LevelText := '[Fatal]';
                Lines.Add(LevelText + ' ' + Violation.DM_DescriptorString + ' ' + Violation.DM_DetailString);
            End;
            If Ok Then Lines.Add('DM_Compile_return=True')
            Else Lines.Add('DM_Compile_return=False');
            If Cancelled Then Lines.Add('Cancelled=True') Else Lines.Add('Cancelled=False');
            Lines.Add('Complete');
            Lines.SaveToFile('__STATUS__');
            Lines.Clear;
            Messages := Workspace.DM_MessagesManager;
            For J := 0 To Messages.MessagesCount - 1 Do
            Begin
                Item := Messages.Messages(J);
                Lines.Add('[' + Item.MsgClass + '] ' + Item.Text);
            End;
            Lines.SaveToFile('__MESSAGES__');
            Lines.Free;
        End;
    End;
    If Not Found Then
    Begin
        Lines := TStringList.Create;
        Lines.Add('Failed=Project not found in workspace: ' + Requested);
        Lines.SaveToFile('__STATUS__');
        Lines.Free;
    End;
    Inputs.Free;
End;
