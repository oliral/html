Imports System.Drawing
Imports System.Windows.Forms

Public Class Form1
    Inherits Form

    Private rnd As New Random()

    Private cellCountX As Integer = 25
    Private cellCountY As Integer = 18

    Private maze(cellCountX - 1, cellCountY - 1) As Cell

    Private Enum Dir
        Top = 0
        Right = 1
        Bottom = 2
        Left = 3
    End Enum

    Private Structure Cell
        Public Walls As Boolean() ' 0..3
        Public Visited As Boolean

        Public Shared Function Create() As Cell
            Dim c As New Cell()
            c.Walls = New Boolean(3) {}
            For i = 0 To 3
                c.Walls(i) = True
            Next
            c.Visited = False
            Return c
        End Function
    End Structure

    Public Sub New()
        Me.Text = "Random Maze"
        Me.DoubleBuffered = True
        Me.ClientSize = New Size(1000, 700)

        AddHandler Me.MouseDown,
            Sub()
                GenerateAndRender()
                Me.Invalidate()
            End Sub

        GenerateAndRender()
    End Sub

    Private Sub GenerateAndRender()
        ReDim maze(cellCountX - 1, cellCountY - 1)

        For y = 0 To cellCountY - 1
            For x = 0 To cellCountX - 1
                maze(x, y) = Cell.Create()
            Next
        Next

        CarveMaze()
    End Sub

    Private Sub CarveMaze()
        Dim stack As New Stack(Of (x As Integer, y As Integer))

        Dim startX = 0
        Dim startY = 0

        maze(startX, startY).Visited = True
        stack.Push((startX, startY))

        While stack.Count > 0
            Dim cur = stack.Peek()
            Dim cx = cur.x
            Dim cy = cur.y

            Dim neighbors As New List(Of (nx As Integer, ny As Integer, dir As Dir))

            If cy > 0 AndAlso Not maze(cx, cy - 1).Visited Then neighbors.Add((cx, cy - 1, Dir.Top))
            If cx < cellCountX - 1 AndAlso Not maze(cx + 1, cy).Visited Then neighbors.Add((cx + 1, cy, Dir.Right))
            If cy < cellCountY - 1 AndAlso Not maze(cx, cy + 1).Visited Then neighbors.Add((cx, cy + 1, Dir.Bottom))
            If cx > 0 AndAlso Not maze(cx - 1, cy).Visited Then neighbors.Add((cx - 1, cy, Dir.Left))

            If neighbors.Count = 0 Then
                stack.Pop()
            Else
                Dim chosen = neighbors(rnd.Next(neighbors.Count)) ' <-- correct parenthesis
                Dim nx = chosen.nx
                Dim ny = chosen.ny
                Dim dir = chosen.dir

                RemoveWall(cx, cy, dir)

                maze(nx, ny).Visited = True
                stack.Push((nx, ny))
            End If
        End While
    End Sub

    Private Sub RemoveWall(cx As Integer, cy As Integer, dir As Dir)
        Select Case dir
            Case Dir.Top
                maze(cx, cy).Walls(CInt(Dir.Top)) = False
                maze(cx, cy - 1).Walls(CInt(Dir.Bottom)) = False
            Case Dir.Right
                maze(cx, cy).Walls(CInt(Dir.Right)) = False
                maze(cx + 1, cy).Walls(CInt(Dir.Left)) = False
            Case Dir.Bottom
                maze(cx, cy).Walls(CInt(Dir.Bottom)) = False
                maze(cx, cy + 1).Walls(CInt(Dir.Top)) = False
            Case Dir.Left
                maze(cx, cy).Walls(CInt(Dir.Left)) = False
                maze(cx - 1, cy).Walls(CInt(Dir.Right)) = False
        End Select
    End Sub

    Protected Overrides Sub OnPaint(e As PaintEventArgs)
        MyBase.OnPaint(e)

        Dim g = e.Graphics
        g.Clear(Color.White)

        Dim margin As Integer = 20
        Dim availableW = Me.ClientSize.Width - 2 * margin
        Dim availableH = Me.ClientSize.Height - 2 * margin
        If availableW <= 10 OrElse availableH <= 10 Then Return

        Dim cellSizeX As Integer = availableW \ cellCountX
        Dim cellSizeY As Integer = availableH \ cellCountY
        Dim cellSize As Integer = Math.Max(5, Math.Min(cellSizeX, cellSizeY))

        Dim originX As Integer = (Me.ClientSize.Width - cellCountX * cellSize) \ 2
        Dim originY As Integer = (Me.ClientSize.Height - cellCountY * cellSize) \ 2

        Using pen As New Pen(Color.Black, 2)
            For y = 0 To cellCountY - 1
                For x = 0 To cellCountX - 1
                    Dim left = originX + x * cellSize
                    Dim top = originY + y * cellSize
                    Dim right = left + cellSize
                    Dim bottom = top + cellSize

                    If maze(x, y).Walls(CInt(Dir.Top)) Then g.DrawLine(pen, left, top, right, top)
                    If maze(x, y).Walls(CInt(Dir.Right)) Then g.DrawLine(pen, right, top, right, bottom)
                    If maze(x, y).Walls(CInt(Dir.Bottom)) Then g.DrawLine(pen, left, bottom, right, bottom)
                    If maze(x, y).Walls(CInt(Dir.Left)) Then g.DrawLine(pen, left, top, left, bottom)
                Next
            Next
        End Using
    End Sub
End Class
